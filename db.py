import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "productos.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            contacto TEXT,
            notas TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            proveedor_id INTEGER REFERENCES proveedores(id),
            costo REAL NOT NULL DEFAULT 0,
            precio_venta REAL DEFAULT 0,
            margen_porcentaje REAL DEFAULT 0,
            iva_porcentaje REAL DEFAULT 21,
            categoria TEXT,
            stock INTEGER DEFAULT 0,
            activo INTEGER DEFAULT 1,
            publicar INTEGER DEFAULT 0,
            costo_usd REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS imagenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
            archivo TEXT NOT NULL,
            es_principal INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nombre TEXT NOT NULL,
            cliente_email TEXT NOT NULL,
            cliente_telefono TEXT DEFAULT '',
            cliente_direccion TEXT DEFAULT '',
            total REAL NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            mp_preference_id TEXT DEFAULT '',
            mp_payment_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS pedido_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
            producto_id INTEGER DEFAULT NULL,
            nombre TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            precio_unitario REAL NOT NULL,
            subtotal REAL NOT NULL
        );
    """)
    conn.commit()
    # Migrations for existing databases
    for col in ["publicar", "costo_usd", "referencia"]:
        tipo = "TEXT DEFAULT ''" if col == "referencia" else ("REAL DEFAULT 0" if col == "costo_usd" else "INTEGER DEFAULT 0")
        try:
            conn.execute(f"ALTER TABLE productos ADD COLUMN {col} {tipo}")
            conn.commit()
        except Exception:
            pass
    conn.close()


def add_proveedor(nombre, contacto="", notas=""):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO proveedores (nombre, contacto, notas) VALUES (?, ?, ?)",
            (nombre, contacto, notas),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_proveedores():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_proveedor(proveedor_id, nombre=None, contacto=None, notas=None):
    updates = {}
    if nombre is not None:
        updates["nombre"] = nombre
    if contacto is not None:
        updates["contacto"] = contacto
    if notas is not None:
        updates["notas"] = notas
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [proveedor_id]
    conn = get_connection()
    conn.execute(f"UPDATE proveedores SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True


def add_producto(nombre, descripcion, proveedor_id, costo, categoria="",
                 stock=0, iva_porcentaje=21, publicar=0):
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO productos
           (nombre, descripcion, proveedor_id, costo, categoria, stock, iva_porcentaje, publicar)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (nombre, descripcion, proveedor_id, costo, categoria, stock, iva_porcentaje, publicar),
    )
    conn.commit()
    product_id = cur.lastrowid
    conn.close()
    return product_id


def get_productos(activos=True, proveedor_id=None, categoria=None, publicado_only=False):
    conn = get_connection()
    query = """
        SELECT p.*, pr.nombre as proveedor_nombre
        FROM productos p
        LEFT JOIN proveedores pr ON p.proveedor_id = pr.id
        WHERE 1=1
    """
    params = []
    if activos:
        query += " AND p.activo = 1"
    if proveedor_id:
        query += " AND p.proveedor_id = ?"
        params.append(proveedor_id)
    if categoria:
        query += " AND p.categoria = ?"
        params.append(categoria)
    if publicado_only:
        query += " AND p.publicar = 1"
    query += " ORDER BY p.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_producto(producto_id):
    conn = get_connection()
    row = conn.execute(
        """SELECT p.*, pr.nombre as proveedor_nombre
           FROM productos p
           LEFT JOIN proveedores pr ON p.proveedor_id = pr.id
           WHERE p.id = ?""",
        (producto_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_producto(producto_id, **kwargs):
    allowed = {"nombre", "descripcion", "costo", "precio_venta", "margen_porcentaje",
               "iva_porcentaje", "categoria", "stock", "activo", "proveedor_id", "publicar",
               "costo_usd"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [producto_id]
    conn = get_connection()
    conn.execute(f"UPDATE productos SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True


def delete_producto(producto_id):
    conn = get_connection()
    conn.execute("DELETE FROM productos WHERE id = ?", (producto_id,))
    conn.commit()
    conn.close()


def add_imagen(producto_id, archivo, es_principal=False):
    conn = get_connection()
    if es_principal:
        conn.execute(
            "UPDATE imagenes SET es_principal = 0 WHERE producto_id = ?",
            (producto_id,),
        )
    conn.execute(
        "INSERT INTO imagenes (producto_id, archivo, es_principal) VALUES (?, ?, ?)",
        (producto_id, archivo, int(es_principal)),
    )
    conn.commit()
    conn.close()


def get_imagenes(producto_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM imagenes WHERE producto_id = ? ORDER BY es_principal DESC",
        (producto_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Pedidos ───────────────────────────────────────────────────────

def crear_pedido(cliente_nombre, cliente_email, cliente_telefono,
                 cliente_direccion, total, items):
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO pedidos
           (cliente_nombre, cliente_email, cliente_telefono, cliente_direccion, total)
           VALUES (?, ?, ?, ?, ?)""",
        (cliente_nombre, cliente_email, cliente_telefono, cliente_direccion, total),
    )
    pedido_id = cur.lastrowid
    for item in items.values():
        conn.execute(
            """INSERT INTO pedido_items
               (pedido_id, producto_id, nombre, cantidad, precio_unitario, subtotal)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pedido_id, item.get("producto_id"), item["nombre"],
             item["cantidad"], item["precio"],
             item["precio"] * item["cantidad"]),
        )
    conn.commit()
    conn.close()
    return pedido_id


def get_pedido(pedido_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pedido_items(pedido_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pedido_items WHERE pedido_id = ?", (pedido_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pedidos(estado=None):
    conn = get_connection()
    query = "SELECT * FROM pedidos"
    params = []
    if estado:
        query += " WHERE estado = ?"
        params.append(estado)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def actualizar_pedido_mp(pedido_id, mp_preference_id=""):
    conn = get_connection()
    conn.execute(
        "UPDATE pedidos SET mp_preference_id = ?, updated_at = datetime('now','localtime') WHERE id = ?",
        (mp_preference_id, pedido_id),
    )
    conn.commit()
    conn.close()


def actualizar_estado_pedido(pedido_id, estado, mp_payment_id=""):
    conn = get_connection()
    conn.execute(
        """UPDATE pedidos SET estado = ?, mp_payment_id = ?,
           updated_at = datetime('now','localtime') WHERE id = ?""",
        (estado, mp_payment_id, pedido_id),
    )
    conn.commit()
    conn.close()
