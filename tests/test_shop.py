"""Regression tests. All data/configuration live in an isolated temporary directory."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

_TEMP = tempfile.TemporaryDirectory()
os.environ.update(APP_DATA_DIR=_TEMP.name, DATABASE_PATH=os.path.join(_TEMP.name, 'shop.db'),
                  DATABASE_URL='', SESSION_SECRET='test-session-secret', ADMIN_PASSWORD='test-password',
                  BANCO_ALIAS='cuenta.de.prueba', TELEGRAM_BOT_TOKEN='', RAILWAY_ENVIRONMENT='')
import db
import config
import web
import precios


class ShopTest(unittest.TestCase):
    def setUp(self):
        conn = db.get_connection()
        for table in ('pedido_items', 'pedidos', 'clicks_afiliados', 'imagenes', 'productos', 'proveedores'):
            conn.execute(f'DELETE FROM {table}')
        conn.commit()
        conn.close()
        db.add_proveedor('Proveedor de prueba')
        self.product = db.add_producto('Producto de prueba', '', None, 50, stock=2, publicar=1)
        db.update_producto(self.product, precio_venta=100)
        web.app.config['TESTING'] = True
        self.client = web.app.test_client()
        self.client.get('/login')
        self.notification = patch('tienda.notificaciones.pedido_nuevo')
        self.notification.start()
        self.addCleanup(self.notification.stop)

    def post(self, path, data=None, client=None):
        client = client or self.client
        with client.session_transaction() as session:
            token = session['csrf_token']
        return client.post(path, data=dict(data or {}, csrf_token=token))

    def cart(self):
        self.post(f'/carrito/agregar/{self.product}', {'cantidad': '1'})
        response = self.client.get('/checkout')
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            return session['checkout_key']

    def checkout(self, key):
        return self.post('/checkout/procesar', dict(nombre='Cliente', email='cliente@example.com', checkout_key=key))

    def items(self, product=None, quantity=1, price=100):
        product = product or self.product
        return {str(product): dict(producto_id=product, nombre='stale', cantidad=quantity, precio=price)}

    def order(self, key='key', items=None):
        return db.crear_pedido('Cliente', 'cliente@example.com', '', '', 99999, items or self.items(), key)

    def test_transfer_checkout_privacy_and_duplicate(self):
        key = self.cart()
        response = self.checkout(key)
        self.assertEqual(response.status_code, 302)
        order = db.get_pedidos()[0]
        self.assertEqual(order['estado'], 'pendiente')
        self.assertEqual(order['total'], 100)
        self.assertEqual(db.get_producto(self.product)['stock'], 1)
        page = self.client.get(response.location)
        self.assertIn(b'cuenta.de.prueba', page.data)
        self.assertEqual(self.client.get(response.location).status_code, 200)
        stranger = web.app.test_client()
        self.assertEqual(stranger.get(response.location).status_code, 404)
        self.assertEqual(self.checkout(key).location, response.location)
        self.assertEqual(len(db.get_pedidos()), 1)
        self.assertEqual(db.get_producto(self.product)['stock'], 1)
        self.assertEqual(page.headers['Cache-Control'], 'no-store')

    def test_price_changed_requires_review(self):
        key = self.cart()
        db.update_producto(self.product, precio_venta=150)
        self.assertTrue(self.checkout(key).location.endswith('/carrito'))
        self.assertEqual(db.get_pedidos(), [])
        self.client.get('/carrito')
        self.client.get('/checkout')
        with self.client.session_transaction() as session:
            key = session['checkout_key']
        self.checkout(key)
        self.assertEqual(db.get_pedidos()[0]['total'], 150)

    def test_unpublished_and_external_rejected(self):
        for updates in ({'publicar': 0}, {'publicar': 1, 'es_afiliado': 1}):
            db.update_producto(self.product, **updates)
            with self.assertRaises(db.PedidoError):
                self.order()
            self.post(f'/carrito/agregar/{self.product}', {'cantidad': 1})
            with self.client.session_transaction() as session:
                self.assertFalse(session.get('carrito'))

    def test_atomic_rollback(self):
        second = db.add_producto('Agotado', '', None, 50, stock=0, publicar=1)
        db.update_producto(second, precio_venta=100)
        items = self.items() | self.items(second)
        with self.assertRaises(db.PedidoError):
            self.order(items=items)
        self.assertEqual(db.get_pedidos(), [])
        self.assertEqual(db.get_producto(self.product)['stock'], 2)

    def test_two_buyers_last_item(self):
        db.update_producto(self.product, stock=1)
        def attempt(key):
            try:
                return self.order(key)
            except db.PedidoError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ['buyer-a', 'buyer-b']))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(db.get_producto(self.product)['stock'], 0)

    def test_same_request_concurrently_is_one_order(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.order, ['same-key', 'same-key']))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(db.get_pedidos()), 1)
        self.assertEqual(db.get_producto(self.product)['stock'], 1)

    def test_cancel_restores_once_and_payment_does_not_deduct_twice(self):
        order_id = self.order()
        self.assertTrue(db.actualizar_estado_pedido(order_id, 'pagado'))
        self.assertFalse(db.actualizar_estado_pedido(order_id, 'pagado'))
        self.assertEqual(db.get_producto(self.product)['stock'], 1)
        self.assertTrue(db.actualizar_estado_pedido(order_id, 'cancelado'))
        self.assertFalse(db.actualizar_estado_pedido(order_id, 'cancelado'))
        self.assertEqual(db.get_producto(self.product)['stock'], 2)
        with self.assertRaises(db.PedidoError):
            db.actualizar_estado_pedido(order_id, 'pagado')

    def test_legacy_cancel_does_not_increase_stock(self):
        conn = db.get_connection()
        conn.execute("INSERT INTO pedidos (cliente_nombre, cliente_email, total) VALUES ('Legacy', 'legacy@example.com', 100)")
        conn.commit()
        conn.close()
        order_id = db.get_pedidos()[0]['id']
        db.actualizar_estado_pedido(order_id, 'cancelado')
        self.assertEqual(db.get_producto(self.product)['stock'], 2)

    def test_csrf_and_invalid_quantity(self):
        self.assertEqual(self.client.post(f'/carrito/agregar/{self.product}').status_code, 400)
        for quantity in ('abc', '0', '-1', '1.5'):
            self.assertEqual(self.post(f'/carrito/agregar/{self.product}', {'cantidad': quantity}).status_code, 400)

    def test_admin_and_public_pages(self):
        self.assertEqual(self.client.get('/productos').status_code, 302)
        self.post('/login', {'password': 'test-password'})
        order_id = self.order()
        for path in ('/tienda', f'/tienda/{self.product}', '/nosotros', '/productos', '/productos/nuevo',
                     f'/productos/{self.product}/editar', '/proveedores', '/categorias', '/precios',
                     '/pedidos', f'/pedidos/{order_id}', '/configuracion', '/contenido', '/contenido/afiliados'):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.post('/precios', {'costo': 100, 'margen_deseado': 100}).status_code, 200)

    def test_migrations_idempotent_and_soft_delete(self):
        db.init_db()
        db.init_db()
        self.order()
        db.delete_producto(self.product)
        self.assertEqual(db.get_producto(self.product)['activo'], 0)
        self.assertEqual(len(db.get_pedidos()), 1)

    def test_ajax_metadata_csrf_header(self):
        self.post('/login', {'password': 'test-password'})
        with self.client.session_transaction() as session:
            token = session['csrf_token']
        with patch('web.itgr.fetch_metadata', return_value={'ok': True}):
            response = self.client.post('/productos/fetch-metadata', data={'url': 'https://example.com'},
                                        headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 200)

    def test_seed_preserves_existing_catalog(self):
        import json
        import seed_railway
        path = os.path.join(_TEMP.name, 'seed.json')
        data = {'proveedores': [], 'productos': [], 'imagenes': []}
        with open(path, 'w') as f:
            json.dump(data, f)
        before = db.get_producto(self.product)
        with patch('seed_railway._seed_affiliate_products') as sync:
            seed_railway.seed_from_file(path)
            sync.assert_not_called()
        self.assertEqual(db.get_producto(self.product), before)

    def test_seed_empty_database(self):
        import seed_railway
        conn = db.get_connection()
        conn.execute('DELETE FROM productos')
        conn.execute('DELETE FROM proveedores')
        conn.commit()
        seed_railway.seed_database(conn, {
            'proveedores': [{'id': 1, 'nombre': 'Proveedor inicial'}],
            'productos': [{'id': 1, 'nombre': 'Inicial', 'proveedor_id': 1, 'costo': 50, 'precio_venta': 100}],
            'imagenes': [],
        })
        conn.commit()
        conn.close()
        self.assertEqual(db.get_producto(1)['nombre'], 'Inicial')

    def test_legacy_payment_reserves_stock(self):
        conn = db.get_connection()
        conn.execute("INSERT INTO pedidos (cliente_nombre, cliente_email, total) VALUES ('Legacy', 'legacy@example.com', 100)")
        order_id = conn.execute('SELECT id FROM pedidos').fetchone()['id']
        conn.execute("INSERT INTO pedido_items (pedido_id, producto_id, nombre, cantidad, precio_unitario, subtotal) VALUES (?, ?, 'Producto', 1, 100, 100)",
                     (order_id, self.product))
        conn.commit()
        conn.close()
        db.actualizar_estado_pedido(order_id, 'pagado')
        self.assertEqual(db.get_producto(self.product)['stock'], 1)
        db.actualizar_estado_pedido(order_id, 'cancelado')
        self.assertEqual(db.get_producto(self.product)['stock'], 2)

    def test_persistent_secret_and_price_validation(self):
        with patch.dict(os.environ, {'SESSION_SECRET': ''}):
            first = config.session_secret()
            self.assertEqual(first, config.session_secret())
        for margin in (100, 101, -1, float('nan')):
            with self.assertRaises(ValueError):
                precios.calcular_precio_venta_rapido(100, margin)


if __name__ == '__main__':
    unittest.main()
