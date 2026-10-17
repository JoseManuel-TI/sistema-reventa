"""
Database layer — supports SQLite (local) and PostgreSQL (Railway).
Auto-detects PostgreSQL when DATABASE_URL env var is set.
"""

import os
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL) and not DATABASE_URL.strip().startswith("sqlite")

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.environ.get("APP_DATA_DIR")
if not DATA_DIR and os.environ.get("RAILWAY_ENVIRONMENT"):
    DATA_DIR = "/data"
DATA_DIR = DATA_DIR or os.path.join(BASE_DIR, "data")

if USE_POSTGRES:
    import psycopg2
    from psycopg2 import errors as pg_errors
    from psycopg2.extras import RealDictCursor

    DB_PATH = DATABASE_URL
    IntegrityError = pg_errors.UniqueViolation

    class _PGConnection:
        """Adapta la connection de psycopg2 a la API de sqlite3 (conn.execute).

        psycopg2 no expone `.execute()` en la connection, así que delegamos en
        un cursor de corta vida para cada llamada. Mantiene commit/rollback/close.
        """

        def __init__(self, conn):
            self._conn = conn

        def execute(self, query, params=None):
            cur = self._conn.cursor()
            if params is not None:
                cur.execute(query, params)
            else:
                cur.execute(query)
            return cur

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

        def close(self):
            return self._conn.close()

    def get_connection():
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        conn.autocommit = False
        return _PGConnection(conn)

    def _sql(q):
        return q.replace("?", "%s")

    def _insert_and_get_id(conn, query, params):
        q = _sql(query).rstrip(";") + " RETURNING id"
        cur = conn.execute(q, params)
        return cur.fetchone()["id"]

else:
    import sqlite3

    DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(DATA_DIR, "productos.db")
    IntegrityError = sqlite3.IntegrityError

    def get_connection():
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=20000")
        return conn

    def _sql(q):
        return q

    def _insert_and_get_id(conn, query, params):
        cur = conn.execute(query, params)
        return cur.lastrowid

def _warn_persist():
    if USE_POSTGRES:
        return
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        test_f = os.path.join(DATA_DIR, ".write_test")
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(test_f, "w") as f:
                f.write("ok")
            os.remove(test_f)
        except OSError:
            print("⚠  Railway Volume no detectado — los datos NO persistirán tras un deploy.")
            print("   Creá un Volume en https://railway.com/project/volumes montado en /data")


_warn_persist()


def execute(conn, query, params=None):
    """Execute query adapting placeholders for the active backend."""
    q = _sql(query)
    if params is not None:
        return conn.execute(q, params)
    return conn.execute(q)


def init_db():
    conn = get_connection()
    try:
        if USE_POSTGRES:
            for ddl in [
                """CREATE TABLE IF NOT EXISTS proveedores (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL UNIQUE,
                    contacto TEXT DEFAULT '',
                    notas TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE TABLE IF NOT EXISTS categorias (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE TABLE IF NOT EXISTS productos (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    descripcion TEXT DEFAULT '',
                    proveedor_id INTEGER REFERENCES proveedores(id),
                    costo DOUBLE PRECISION NOT NULL DEFAULT 0,
                    precio_venta DOUBLE PRECISION DEFAULT 0,
                    margen_porcentaje DOUBLE PRECISION DEFAULT 0,
                    iva_porcentaje DOUBLE PRECISION DEFAULT 21,
                    categoria TEXT DEFAULT '',
                    stock INTEGER DEFAULT 0,
                    activo INTEGER DEFAULT 1,
                    publicar INTEGER DEFAULT 0,
                    costo_usd DOUBLE PRECISION DEFAULT 0,
                    es_afiliado BOOLEAN DEFAULT FALSE,
                    link_afiliado TEXT DEFAULT '',
                    plataforma_afiliado TEXT DEFAULT 'amazon',
                    tipo_producto TEXT DEFAULT 'fisico_local',
                    moneda TEXT DEFAULT 'ARS',
                    external_url TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE TABLE IF NOT EXISTS imagenes (
                    id SERIAL PRIMARY KEY,
                    producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
                    archivo TEXT NOT NULL,
                    es_principal INTEGER DEFAULT 0
                )""",
                """CREATE TABLE IF NOT EXISTS pedidos (
                    id SERIAL PRIMARY KEY,
                    cliente_nombre TEXT NOT NULL,
                    cliente_email TEXT NOT NULL,
                    cliente_telefono TEXT DEFAULT '',
                    cliente_direccion TEXT DEFAULT '',
                    total DOUBLE PRECISION NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'pendiente',
                    metodo_pago TEXT DEFAULT 'transferencia',
                    metodo_cobro TEXT DEFAULT '',
                    cobrado INTEGER DEFAULT 0,
                    reserva_expira TEXT DEFAULT '',
                    mp_preference_id TEXT DEFAULT '',
                    mp_payment_id TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE TABLE IF NOT EXISTS pedido_items (
                    id SERIAL PRIMARY KEY,
                    pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
                    producto_id INTEGER DEFAULT NULL,
                    nombre TEXT NOT NULL,
                    cantidad INTEGER NOT NULL,
                    precio_unitario DOUBLE PRECISION NOT NULL,
                    subtotal DOUBLE PRECISION NOT NULL
                )""",
            ]:
                conn.execute(ddl)
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS proveedores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE,
                    contacto TEXT,
                    notas TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS categorias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL UNIQUE,
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
                    es_afiliado INTEGER DEFAULT 0,
                    link_afiliado TEXT DEFAULT '',
                    plataforma_afiliado TEXT DEFAULT 'amazon',
                    tipo_producto TEXT DEFAULT 'fisico_local',
                    moneda TEXT DEFAULT 'ARS',
                    external_url TEXT DEFAULT '',
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
                    metodo_pago TEXT DEFAULT 'transferencia',
                    metodo_cobro TEXT DEFAULT '',
                    cobrado INTEGER DEFAULT 0,
                    reserva_expira TEXT DEFAULT '',
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

        for col, typ in [("publicar", "INTEGER DEFAULT 0"), ("costo_usd", "REAL DEFAULT 0"), ("referencia", "TEXT DEFAULT ''"),
                        ("es_afiliado", "INTEGER DEFAULT 0"), ("link_afiliado", "TEXT DEFAULT ''"),
                        ("plataforma_afiliado", "TEXT DEFAULT 'amazon'"),
                        ("tipo_producto", "TEXT DEFAULT 'fisico_local'"),
                        ("moneda", "TEXT DEFAULT 'ARS'"),
                        ("external_url", "TEXT DEFAULT ''"),
                        ("beneficios", "TEXT DEFAULT ''")]:
            try:
                conn.execute(f"ALTER TABLE productos ADD COLUMN {col} {typ}")
                conn.commit()
            except Exception:
                # La columna ya existe. En Postgres un error aborta la transacción,
                # así que hacemos rollback para no romper los ALTER siguientes.
                conn.rollback()

        for col, typ in [("metodo_pago", "TEXT DEFAULT 'transferencia'"),
                         ("metodo_cobro", "TEXT DEFAULT ''"),
                         ("cobrado", "INTEGER DEFAULT 0"),
                         ("reserva_expira", "TEXT DEFAULT ''")]:
            try:
                conn.execute(f"ALTER TABLE pedidos ADD COLUMN {col} {typ}")
                conn.commit()
            except Exception:
                conn.rollback()

        ensure_proveedor_amazon()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Proveedores ──────────────────────────────────────────────────

def add_proveedor(nombre, contacto="", notas=""):
    conn = get_connection()
    try:
        new_id = _insert_and_get_id(
            conn,
            "INSERT INTO proveedores (nombre, contacto, notas) VALUES (?, ?, ?)",
            (nombre, contacto, notas),
        )
        conn.commit()
        return new_id
    except IntegrityError:
        return None
    finally:
        conn.close()


def get_proveedores():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_proveedor_por_nombre(nombre):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM proveedores WHERE LOWER(nombre) = LOWER(?) LIMIT 1", (nombre,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def ensure_proveedor_amazon():
    prov = get_proveedor_por_nombre("Amazon")
    if prov:
        return prov
    return add_proveedor("Amazon", contacto="", notas="Afiliados Amazon")


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
    try:
        conn.execute(f"UPDATE proveedores SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return True
    finally:
        conn.close()


def delete_proveedor(proveedor_id):
    """Elimina un proveedor, desvinculando primero sus productos."""
    conn = get_connection()
    try:
        conn.execute(_sql("UPDATE productos SET proveedor_id = NULL WHERE proveedor_id = ?"), (proveedor_id,))
        conn.execute(_sql("DELETE FROM proveedores WHERE id = ?"), (proveedor_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ─── Categorías ──────────────────────────────────────────────────

def add_categoria(nombre):
    nombre = (nombre or "").strip()
    if not nombre:
        return None
    conn = get_connection()
    try:
        new_id = _insert_and_get_id(
            conn,
            "INSERT INTO categorias (nombre) VALUES (?)",
            (nombre,),
        )
        conn.commit()
        return new_id
    except IntegrityError:
        return None
    finally:
        conn.close()


def get_categorias_admin():
    """Categorías de la tabla manual, con cantidad de productos asignados."""
    conn = get_connection()
    try:
        rows = conn.execute(_sql("""
            SELECT c.id, c.nombre,
                   (SELECT COUNT(*) FROM productos p WHERE p.categoria = c.nombre) as cantidad_productos
            FROM categorias c
            ORDER BY c.nombre
        """)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_categoria(nombre):
    """Borra la categoría y limpia el campo categoria de los productos que la usen."""
    conn = get_connection()
    try:
        conn.execute(_sql("UPDATE productos SET categoria = '' WHERE categoria = ?"), (nombre,))
        conn.execute(_sql("DELETE FROM categorias WHERE nombre = ?"), (nombre,))
        conn.commit()
        return True
    finally:
        conn.close()


# ─── Productos ────────────────────────────────────────────────────

def add_producto(nombre, descripcion, proveedor_id, costo, categoria="",
                 stock=0, iva_porcentaje=21, publicar=0,
                 es_afiliado=0, link_afiliado="", beneficios="", plataforma_afiliado="amazon",
                 tipo_producto="fisico_local", moneda="ARS", external_url=""):
    conn = get_connection()
    try:
        product_id = _insert_and_get_id(
            conn,
            """INSERT INTO productos
               (nombre, descripcion, proveedor_id, costo, categoria, stock, iva_porcentaje, publicar,
                es_afiliado, link_afiliado, beneficios, plataforma_afiliado, tipo_producto, moneda, external_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nombre, descripcion, proveedor_id, costo, categoria, stock, iva_porcentaje, publicar,
             es_afiliado, link_afiliado, beneficios, plataforma_afiliado or "amazon",
             tipo_producto or "fisico_local", moneda or "ARS", external_url or link_afiliado or ""),
        )
        conn.commit()
        return product_id
    finally:
        conn.close()


def get_productos(activos=True, proveedor_id=None, categoria=None, publicado_only=False):
    conn = get_connection()
    try:
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
        rows = conn.execute(_sql(query), params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_producto(producto_id):
    conn = get_connection()
    try:
        row = conn.execute(
            _sql("""SELECT p.*, pr.nombre as proveedor_nombre
               FROM productos p
               LEFT JOIN proveedores pr ON p.proveedor_id = pr.id
               WHERE p.id = ?"""),
            (producto_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_categorias(publicado_only=False):
    """Devuelve las categorías distintas de productos, ordenadas."""
    conn = get_connection()
    try:
        query = """SELECT DISTINCT categoria FROM productos
                   WHERE categoria IS NOT NULL AND categoria != ''"""
        params = []
        if publicado_only:
            query += " AND activo = 1 AND publicar = 1"
        query += " ORDER BY categoria"
        rows = conn.execute(_sql(query), params).fetchall()
        return [r[0] for r in rows if r[0]]
    finally:
        conn.close()


def update_producto(producto_id, **kwargs):
    allowed = {"nombre", "descripcion", "costo", "precio_venta", "margen_porcentaje",
               "iva_porcentaje", "categoria", "stock", "activo", "proveedor_id", "publicar",
               "costo_usd", "es_afiliado", "link_afiliado", "beneficios", "plataforma_afiliado",
               "tipo_producto", "moneda", "external_url"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [producto_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE productos SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return True
    finally:
        conn.close()


def delete_producto(producto_id):
    """Borra el producto, sus imágenes y los archivos huérfanos."""
    conn = get_connection()
    try:
        rows = conn.execute(
            _sql("SELECT archivo FROM imagenes WHERE producto_id = ?"), (producto_id,)
        ).fetchall()
        archivos = [r["archivo"] for r in rows]
        conn.execute(_sql("DELETE FROM productos WHERE id = ?"), (producto_id,))
        for archivo in archivos:
            ref = conn.execute(
                _sql("SELECT COUNT(*) AS c FROM imagenes WHERE archivo = ?"), (archivo,)
            ).fetchone()
            restantes = ref["c"] if ref is not None else 0
            if restantes == 0:
                borrar_archivo_imagen(archivo)
        conn.commit()
    finally:
        conn.close()
    invalidar_index_imagenes()


# ─── Imágenes ─────────────────────────────────────────────────────

def add_imagen(producto_id, archivo, es_principal=False):
    conn = get_connection()
    try:
        if es_principal:
            conn.execute(
                _sql("UPDATE imagenes SET es_principal = 0 WHERE producto_id = ?"),
                (producto_id,),
            )
        conn.execute(
            _sql("INSERT INTO imagenes (producto_id, archivo, es_principal) VALUES (?, ?, ?)"),
            (producto_id, archivo, int(es_principal)),
        )
        conn.commit()
    finally:
        conn.close()


def get_imagenes(producto_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            _sql("SELECT * FROM imagenes WHERE producto_id = ? ORDER BY es_principal DESC"),
            (producto_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def imagenes_dir():
    """Directorio real de las imágenes (persistente en Railway, local en dev)."""
    if os.environ.get("IMAGES_DIR"):
        return os.environ["IMAGES_DIR"]
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return os.path.join(DATA_DIR, "imagenes")
    return os.path.join(BASE_DIR, "imagenes")


def borrar_archivo_imagen(archivo):
    """Borra del disco el archivo de una imagen local (best-effort)."""
    if not archivo or archivo.startswith(("http://", "https://")):
        return False
    rel = archivo[len("imagenes/"):] if archivo.startswith("imagenes/") else archivo
    path = os.path.join(imagenes_dir(), rel)
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def eliminar_imagen(imagen_id):
    """Elimina una imagen y su archivo si ya no está referenciado por otro producto."""
    conn = get_connection()
    try:
        row = conn.execute(
            _sql("SELECT archivo FROM imagenes WHERE id = ?"), (imagen_id,)
        ).fetchone()
        if not row:
            return None
        archivo = row["archivo"]
        conn.execute(_sql("DELETE FROM imagenes WHERE id = ?"), (imagen_id,))
        ref = conn.execute(
            _sql("SELECT COUNT(*) AS c FROM imagenes WHERE archivo = ?"), (archivo,)
        ).fetchone()
        restantes = ref["c"] if ref is not None else 0
        conn.commit()
    finally:
        conn.close()
    if restantes == 0:
        borrar_archivo_imagen(archivo)
    invalidar_index_imagenes()
    return archivo


_IMAGEN_INDEX = None


def _reindex_imagenes():
    """Indexa (basename → rel) de todas las imágenes en disco, una sola vez."""
    global _IMAGEN_INDEX
    if _IMAGEN_INDEX is not None:
        return _IMAGEN_INDEX
    raiz = imagenes_dir()
    indice = {}
    if os.path.isdir(raiz):
        for root, _, files in os.walk(raiz):
            for fname in files:
                indice.setdefault(fname, os.path.join("imagenes", os.path.relpath(root, raiz), fname))
    _IMAGEN_INDEX = indice
    return indice


def invalidar_index_imagenes():
    """Forza re-lectura del índice (después de subir/borrar imágenes)."""
    global _IMAGEN_INDEX
    _IMAGEN_INDEX = None


def normalizar_imagen(archivo):
    """Devuelve la ruta web canónica de una imagen.

    Corrige rutas rotas en la DB (mayúsculas/espacios en la carpeta de proveedor,
    ej. 'PM IMPORTADOS' en vez de la carpeta real). Si no encuentra el archivo,
    busca por nombre de archivo en todo el árbol de imágenes.
    """
    if not archivo:
        return archivo
    if archivo.startswith("http://") or archivo.startswith("https://"):
        return archivo

    basename = os.path.basename(archivo)
    fpath = os.path.join(imagenes_dir(), archivo[len("imagenes/"):] if archivo.startswith("imagenes/") else archivo)
    if os.path.exists(fpath):
        return archivo

    indice = _reindex_imagenes()
    rel = indice.get(basename)
    if rel:
        return rel
    return archivo


def normalizar_imagenes_db():
    """Corrige en la DB las rutas de imagen que no apuntan al archivo real en disco.

    Devuelve la cantidad de rutas corregidas. Idempotente.
    """
    conn = get_connection()
    corregidas = 0
    try:
        rows = conn.execute(_sql("SELECT id, archivo FROM imagenes")).fetchall()
        for row in rows:
            original = row["archivo"]
            corregido = normalizar_imagen(original)
            if corregido != original:
                conn.execute(
                    _sql("UPDATE imagenes SET archivo = ? WHERE id = ?"),
                    (corregido, row["id"]),
                )
                corregidas += 1
        conn.commit()
    finally:
        conn.close()
    return corregidas


# ─── Pedidos ──────────────────────────────────────────────────────

def crear_pedido(cliente_nombre, cliente_email, cliente_telefono,
                 cliente_direccion, total, items,
                 metodo_pago="transferencia", reserva_expira=""):
    """Crea el pedido revalidando stock y precios actuales de la DB.

    Descuenta el stock de cada producto en la misma transacción. El total se
    recalcula en el servidor (no se confía en el carrito de la sesión).
    `metodo_pago` puede ser 'transferencia' o 'contra_entrega'. `reserva_expira`
    es un timestamp ('YYYY-MM-DD HH:MM:SS') tras el cual la reserva de stock se
    libera automáticamente si el pedido sigue pendiente.
    Lanza ValueError si algún producto no existe, no está disponible o no
    tiene stock suficiente.
    """
    conn = get_connection()
    try:
        lineas = []
        for item in items.values():
            pid = item.get("producto_id")
            cantidad = int(item.get("cantidad") or 0)
            if cantidad <= 0:
                raise ValueError("El pedido tiene una cantidad inválida.")

            prod = conn.execute(
                _sql("SELECT id, nombre, precio_venta, stock, activo FROM productos WHERE id = ?"),
                (pid,),
            ).fetchone()
            if not prod:
                raise ValueError(f"El producto '{item.get('nombre') or pid}' ya no existe.")
            prod = dict(prod)
            if not prod.get("activo"):
                raise ValueError(f"El producto '{prod['nombre']}' ya no está disponible.")

            precio = prod.get("precio_venta") or 0
            if precio <= 0:
                raise ValueError(f"El producto '{prod['nombre']}' no tiene precio de venta.")

            stock = prod.get("stock") or 0
            if cantidad > stock:
                raise ValueError(
                    f"Stock insuficiente de '{prod['nombre']}' (disponible: {stock})."
                )

            lineas.append({
                "producto_id": prod["id"],
                "nombre": prod["nombre"],
                "cantidad": cantidad,
                "precio": precio,
                "subtotal": round(precio * cantidad, 2),
            })

        if not lineas:
            raise ValueError("El pedido no tiene productos.")

        total_calc = round(sum(ln["subtotal"] for ln in lineas), 2)

        pedido_id = _insert_and_get_id(
            conn,
            """INSERT INTO pedidos
               (cliente_nombre, cliente_email, cliente_telefono, cliente_direccion, total,
                metodo_pago, reserva_expira)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cliente_nombre, cliente_email, cliente_telefono, cliente_direccion, total_calc,
             metodo_pago or "transferencia", reserva_expira or ""),
        )
        for ln in lineas:
            conn.execute(
                _sql("""INSERT INTO pedido_items
                   (pedido_id, producto_id, nombre, cantidad, precio_unitario, subtotal)
                   VALUES (?, ?, ?, ?, ?, ?)"""),
                (pedido_id, ln["producto_id"], ln["nombre"], ln["cantidad"], ln["precio"], ln["subtotal"]),
            )
            conn.execute(
                _sql("UPDATE productos SET stock = stock - ? WHERE id = ?"),
                (ln["cantidad"], ln["producto_id"]),
            )
        conn.commit()
        return pedido_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_pedido(pedido_id):
    conn = get_connection()
    try:
        row = conn.execute(
            _sql("SELECT * FROM pedidos WHERE id = ?"), (pedido_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_pedido_items(pedido_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            _sql("SELECT * FROM pedido_items WHERE pedido_id = ?"), (pedido_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_pedidos(estado=None):
    conn = get_connection()
    try:
        query = "SELECT * FROM pedidos"
        params = []
        if estado:
            query += " WHERE estado = ?"
            params.append(estado)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(_sql(query), params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def actualizar_pedido_mp(pedido_id, mp_preference_id=""):
    conn = get_connection()
    try:
        if USE_POSTGRES:
            conn.execute(
                "UPDATE pedidos SET mp_preference_id = %s, updated_at = NOW() WHERE id = %s",
                (mp_preference_id, pedido_id),
            )
        else:
            conn.execute(
                "UPDATE pedidos SET mp_preference_id = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (mp_preference_id, pedido_id),
            )
        conn.commit()
    finally:
        conn.close()


def actualizar_estado_pedido(pedido_id, estado, mp_payment_id=""):
    conn = get_connection()
    try:
        if USE_POSTGRES:
            conn.execute(
                "UPDATE pedidos SET estado = %s, mp_payment_id = %s, updated_at = NOW() WHERE id = %s",
                (estado, mp_payment_id, pedido_id),
            )
        else:
            conn.execute(
                """UPDATE pedidos SET estado = ?, mp_payment_id = ?,
                   updated_at = datetime('now','localtime') WHERE id = ?""",
                (estado, mp_payment_id, pedido_id),
            )
        conn.commit()
    finally:
        conn.close()


def actualizar_cobro_pedido(pedido_id, cobrado, metodo_cobro=""):
    """Marca si el pedido fue cobrado y con qué medio (efectivo/transferencia)."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        conn.execute(
            _sql("UPDATE pedidos SET cobrado = ?, metodo_cobro = ?, updated_at = ? WHERE id = ?"),
            (1 if cobrado else 0, metodo_cobro or "", ahora, pedido_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def liberar_reserva_pedido(pedido_id):
    """Cancela un pedido pendiente y devuelve el stock reservado a los productos.

    No toca pedidos ya cancelados ni entregados (evita devolver stock dos veces).
    """
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        pedido = conn.execute(
            _sql("SELECT estado FROM pedidos WHERE id = ?"), (pedido_id,)
        ).fetchone()
        if not pedido:
            return False
        if pedido["estado"] in ("cancelado", "entregado"):
            return False

        items = conn.execute(
            _sql("SELECT producto_id, cantidad FROM pedido_items WHERE pedido_id = ?"),
            (pedido_id,),
        ).fetchall()
        for it in items:
            if it["producto_id"]:
                conn.execute(
                    _sql("UPDATE productos SET stock = stock + ? WHERE id = ?"),
                    (it["cantidad"], it["producto_id"]),
                )
        conn.execute(
            _sql("UPDATE pedidos SET estado = 'cancelado', reserva_expira = '', updated_at = ? WHERE id = ?"),
            (ahora, pedido_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def liberar_reservas_expiradas():
    """Libera el stock de pedidos pendientes cuya reserva ya venció.

    Devuelve la lista de ids liberados.
    """
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        rows = conn.execute(
            _sql("""SELECT id FROM pedidos
               WHERE estado = 'pendiente' AND reserva_expira != '' AND reserva_expira < ?"""),
            (ahora,),
        ).fetchall()
    finally:
        conn.close()
    liberados = []
    for row in rows:
        if liberar_reserva_pedido(row["id"]):
            liberados.append(row["id"])
    return liberados
