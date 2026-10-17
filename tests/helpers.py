"""Utilidades para armar datos de prueba."""


def crear_proveedor(nombre="Proveedor Test"):
    import db
    return db.add_proveedor(nombre)


def crear_producto(nombre="Producto Test", stock=5, precio=100.0, publicar=1,
                   activo=1, proveedor_id=None, costo=50, categoria=""):
    import db
    if proveedor_id is None:
        proveedor_id = crear_proveedor()
    pid = db.add_producto(nombre, "", proveedor_id, costo, categoria, stock, publicar=publicar)
    db.update_producto(pid, precio_venta=precio, activo=activo)
    return pid
