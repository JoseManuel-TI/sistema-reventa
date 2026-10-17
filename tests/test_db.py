import os

import pytest
from helpers import crear_producto, crear_proveedor

import db


def test_proveedor_por_nombre_case_insensitive():
    crear_proveedor("Importados del Sur")
    assert db.get_proveedor_por_nombre("importados DEL sur") is not None
    assert db.get_proveedor_por_nombre("no existe") is None


def test_add_y_get_producto():
    pid = crear_producto(nombre="Auriculares", stock=3, precio=250)
    p = db.get_producto(pid)
    assert p["nombre"] == "Auriculares"
    assert p["stock"] == 3
    assert p["precio_venta"] == 250


def test_update_producto_ignora_claves_no_permitidas():
    pid = crear_producto()
    assert db.update_producto(pid, campo_inventado="x") is False
    assert db.update_producto(pid, nombre="Nuevo") is True
    assert db.get_producto(pid)["nombre"] == "Nuevo"


def test_crear_pedido_descuenta_stock_y_recalcula_total():
    pid = crear_producto(stock=5, precio=100)
    items = {"1": {"producto_id": pid, "cantidad": 2, "nombre": "Producto Test"}}
    pedido_id = db.crear_pedido("Ana", "a@b.com", "11", "Calle 1", 999, items)
    pedido = db.get_pedido(pedido_id)
    assert pedido["total"] == 200
    assert db.get_producto(pid)["stock"] == 3
    assert len(db.get_pedido_items(pedido_id)) == 1


def test_crear_pedido_stock_insuficiente_no_modifica_nada():
    pid = crear_producto(stock=1, precio=100)
    items = {"1": {"producto_id": pid, "cantidad": 5, "nombre": "Producto Test"}}
    with pytest.raises(ValueError, match="Stock insuficiente"):
        db.crear_pedido("Ana", "a@b.com", "11", "Calle 1", 500, items)
    assert db.get_producto(pid)["stock"] == 1
    assert db.get_pedidos() == []


def test_crear_pedido_producto_inexistente():
    items = {"1": {"producto_id": 99999, "cantidad": 1, "nombre": "Fantasma"}}
    with pytest.raises(ValueError):
        db.crear_pedido("Ana", "a@b.com", "11", "Calle 1", 1, items)


def test_crear_pedido_guarda_metodo_pago_y_reserva():
    pid = crear_producto(stock=3, precio=100)
    items = {"1": {"producto_id": pid, "cantidad": 1, "nombre": "Producto Test"}}
    pedido_id = db.crear_pedido("Ana", "a@b.com", "11", "x", 0, items,
                                metodo_pago="contra_entrega",
                                reserva_expira="2999-01-01 00:00:00")
    p = db.get_pedido(pedido_id)
    assert p["metodo_pago"] == "contra_entrega"
    assert p["reserva_expira"] == "2999-01-01 00:00:00"
    assert p["cobrado"] == 0


def test_crear_pedido_suma_envio_al_total_y_guarda_zona():
    pid = crear_producto(stock=3, precio=100)
    items = {"1": {"producto_id": pid, "cantidad": 2, "nombre": "Producto Test"}}
    pedido_id = db.crear_pedido("Ana", "a@b.com", "11", "x", 0, items,
                                zona_envio="caba", envio_costo=3500)
    p = db.get_pedido(pedido_id)
    assert p["total"] == 200 + 3500
    assert p["zona_envio"] == "caba"
    assert p["envio_costo"] == 3500


def test_crear_pedido_ignora_envio_negativo():
    pid = crear_producto(stock=1, precio=100)
    items = {"1": {"producto_id": pid, "cantidad": 1, "nombre": "Producto Test"}}
    pedido_id = db.crear_pedido("Ana", "a@b.com", "11", "x", 0, items, envio_costo=-500)
    assert db.get_pedido(pedido_id)["total"] == 100


def test_liberar_reserva_devuelve_stock_una_sola_vez():
    pid = crear_producto(stock=3, precio=100)
    items = {"1": {"producto_id": pid, "cantidad": 2, "nombre": "Producto Test"}}
    pedido_id = db.crear_pedido("Ana", "a@b.com", "11", "x", 0, items)
    assert db.get_producto(pid)["stock"] == 1
    assert db.liberar_reserva_pedido(pedido_id) is True
    assert db.get_producto(pid)["stock"] == 3
    assert db.get_pedido(pedido_id)["estado"] == "cancelado"
    assert db.liberar_reserva_pedido(pedido_id) is False
    assert db.get_producto(pid)["stock"] == 3


def test_liberar_reservas_expiradas_solo_libera_vencidas():
    pid = crear_producto(stock=2, precio=100)
    items = {"1": {"producto_id": pid, "cantidad": 1, "nombre": "P"}}
    vencido = db.crear_pedido("A", "a@b.com", "", "", 0, dict(items),
                              reserva_expira="2000-01-01 00:00:00")
    vigente = db.crear_pedido("B", "b@b.com", "", "", 0, dict(items),
                              reserva_expira="2999-01-01 00:00:00")
    liberados = db.liberar_reservas_expiradas()
    assert vencido in liberados
    assert vigente not in liberados
    assert db.get_pedido(vencido)["estado"] == "cancelado"
    assert db.get_pedido(vigente)["estado"] == "pendiente"
    assert db.get_producto(pid)["stock"] == 1


def test_actualizar_cobro_pedido():
    pid = crear_producto(stock=1, precio=100)
    items = {"1": {"producto_id": pid, "cantidad": 1, "nombre": "P"}}
    pedido_id = db.crear_pedido("A", "a@b.com", "", "", 0, items)
    db.actualizar_cobro_pedido(pedido_id, True, "efectivo")
    p = db.get_pedido(pedido_id)
    assert p["cobrado"] == 1
    assert p["metodo_cobro"] == "efectivo"


def _crear_archivo_imagen(nombre):
    ruta = os.path.join(db.imagenes_dir(), nombre)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as f:
        f.write(b"\xff\xd8\xff")
    return ruta


def test_delete_producto_elimina_archivo_de_imagen():
    pid = crear_producto()
    db.add_imagen(pid, "imagenes/foto_test.jpg", es_principal=True)
    ruta = _crear_archivo_imagen("foto_test.jpg")
    assert os.path.isfile(ruta)
    db.delete_producto(pid)
    assert not os.path.exists(ruta)
    assert db.get_imagenes(pid) == []


def test_eliminar_imagen_borra_archivo_no_referenciado():
    pid = crear_producto()
    db.add_imagen(pid, "imagenes/sola.jpg")
    imagen_id = db.get_imagenes(pid)[0]["id"]
    ruta = _crear_archivo_imagen("sola.jpg")
    archivo = db.eliminar_imagen(imagen_id)
    assert archivo == "imagenes/sola.jpg"
    assert not os.path.exists(ruta)
    assert db.get_imagenes(pid) == []
