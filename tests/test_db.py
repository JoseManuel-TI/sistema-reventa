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
