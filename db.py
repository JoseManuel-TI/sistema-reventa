"""
Database layer — supports SQLite (local) and PostgreSQL (Railway).
Auto-detects PostgreSQL when DATABASE_URL env var is set.
"""

import hashlib
import os
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

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
    from psycopg2.extras import DictCursor

    class Connection(psycopg2.extensions.connection):
        def execute(self, query, params=None):
            cursor = self.cursor()
            cursor.execute(_sql(query), params)
            return cursor

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
        conn = psycopg2.connect(DATABASE_URL, connection_factory=Connection, cursor_factory=DictCursor)
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
            conn.execute("SELECT pg_advisory_xact_lock(721934)")
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
                    es_afiliado INTEGER DEFAULT 0,
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
                    cliente_entre_calles TEXT DEFAULT '',
                    cliente_localidad TEXT DEFAULT '',
                    cliente_codigo_postal TEXT DEFAULT '',
                    total DOUBLE PRECISION NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'pendiente',
                    metodo_pago TEXT DEFAULT 'transferencia',
                    metodo_cobro TEXT DEFAULT '',
                    cobrado INTEGER DEFAULT 0,
                    reserva_expira TEXT DEFAULT '',
                    zona_envio TEXT DEFAULT '',
                    envio_costo DOUBLE PRECISION DEFAULT 0,
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
                """CREATE TABLE IF NOT EXISTS clicks_afiliados (
                    id SERIAL PRIMARY KEY,
                    producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
                    plataforma TEXT DEFAULT '',
                    destino TEXT NOT NULL,
                    origen TEXT DEFAULT '',
                    referer TEXT DEFAULT '',
                    user_agent TEXT DEFAULT '',
                    ip_hash TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                    cliente_entre_calles TEXT DEFAULT '',
                    cliente_localidad TEXT DEFAULT '',
                    cliente_codigo_postal TEXT DEFAULT '',
                    total REAL NOT NULL,
                    estado TEXT NOT NULL DEFAULT 'pendiente',
                    metodo_pago TEXT DEFAULT 'transferencia',
                    metodo_cobro TEXT DEFAULT '',
                    cobrado INTEGER DEFAULT 0,
                    reserva_expira TEXT DEFAULT '',
                    zona_envio TEXT DEFAULT '',
                    envio_costo REAL DEFAULT 0,
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
                CREATE TABLE IF NOT EXISTS clicks_afiliados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
                    plataforma TEXT DEFAULT '',
                    destino TEXT NOT NULL,
                    origen TEXT DEFAULT '',
                    referer TEXT DEFAULT '',
                    user_agent TEXT DEFAULT '',
                    ip_hash TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );
            """)
        if not USE_POSTGRES:
            conn.execute("BEGIN IMMEDIATE")

        def add_column(table, col, typ):
            if USE_POSTGRES:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")
            else:
                columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
                if col not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

        for col, typ in [("publicar", "INTEGER DEFAULT 0"), ("costo_usd", "REAL DEFAULT 0"),
                         ("referencia", "TEXT DEFAULT ''"), ("es_afiliado", "INTEGER DEFAULT 0"),
                         ("link_afiliado", "TEXT DEFAULT ''"), ("plataforma_afiliado", "TEXT DEFAULT 'amazon'"),
                         ("tipo_producto", "TEXT DEFAULT 'fisico_local'"), ("moneda", "TEXT DEFAULT 'ARS'"),
                         ("external_url", "TEXT DEFAULT ''"), ("beneficios", "TEXT DEFAULT ''")]:
            add_column("productos", col, typ)
        if USE_POSTGRES:
            column = conn.execute("SELECT data_type FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='productos' AND column_name='es_afiliado'").fetchone()
            if column and column["data_type"] == "boolean":
                conn.execute("ALTER TABLE productos ALTER COLUMN es_afiliado DROP DEFAULT")
                conn.execute("ALTER TABLE productos ALTER COLUMN es_afiliado TYPE INTEGER USING es_afiliado::integer")
                conn.execute("ALTER TABLE productos ALTER COLUMN es_afiliado SET DEFAULT 0")

        for col, typ in [("metodo_pago", "TEXT DEFAULT 'transferencia'"),
                         ("metodo_cobro", "TEXT DEFAULT ''"),
                         ("cobrado", "INTEGER DEFAULT 0"),
                         ("reserva_expira", "TEXT DEFAULT ''"),
                         ("zona_envio", "TEXT DEFAULT ''"),
                         ("envio_costo", "REAL DEFAULT 0"),
                         ("cliente_entre_calles", "TEXT DEFAULT ''"),
                         ("cliente_localidad", "TEXT DEFAULT ''"),
                         ("cliente_codigo_postal", "TEXT DEFAULT ''")]:
            add_column("pedidos", col, typ)
        add_column("pedidos", "stock_reservado", "INTEGER NOT NULL DEFAULT 0")
        add_column("pedidos", "checkout_key", "TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS pedidos_checkout_key ON pedidos(checkout_key)")
        conn.commit()

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
        return [r["categoria"] for r in rows if r["categoria"]]
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
    """Da de baja el producto (soft delete) y borra sus imágenes y archivos.

    Se conserva la fila del producto (activo=0) para no romper el historial de
    pedidos; las imágenes asociadas sí se eliminan del disco.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            _sql("SELECT archivo FROM imagenes WHERE producto_id = ?"), (producto_id,)
        ).fetchall()
        archivos = [r["archivo"] for r in rows]
        conn.execute(_sql("DELETE FROM imagenes WHERE producto_id = ?"), (producto_id,))
        conn.execute(
            _sql("UPDATE productos SET activo = 0, publicar = 0 WHERE id = ?"), (producto_id,)
        )
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


# ─── Tracking afiliados ────────────────────────────────────────────

def registrar_click_afiliado(producto_id, plataforma, destino, origen="", referer="", user_agent="", ip_hash=""):
    conn = get_connection()
    try:
        _insert_and_get_id(
            conn,
            """
            INSERT INTO clicks_afiliados
                (producto_id, plataforma, destino, origen, referer, user_agent, ip_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (producto_id, plataforma or "", destino, origen or "", referer or "", user_agent or "", ip_hash or ""),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_clicks_afiliados_stats(limit=20):
    conn = get_connection()
    try:
        if USE_POSTGRES:
            query = """
            SELECT
                p.id AS producto_id,
                p.nombre AS producto_nombre,
                COALESCE(p.plataforma_afiliado, c.plataforma) AS plataforma,
                COUNT(c.id) AS clicks_total,
                SUM(CASE WHEN c.created_at::date = CURRENT_DATE THEN 1 ELSE 0 END) AS clicks_hoy,
                MAX(c.created_at) AS ultimo_click
            FROM clicks_afiliados c
            LEFT JOIN productos p ON p.id = c.producto_id
            GROUP BY p.id, p.nombre, p.plataforma_afiliado, c.plataforma
            ORDER BY clicks_total DESC, ultimo_click DESC
            LIMIT ?
            """
        else:
            query = """
            SELECT
                p.id AS producto_id,
                p.nombre AS producto_nombre,
                COALESCE(p.plataforma_afiliado, c.plataforma) AS plataforma,
                COUNT(c.id) AS clicks_total,
                SUM(CASE WHEN date(c.created_at) = date('now') THEN 1 ELSE 0 END) AS clicks_hoy,
                MAX(c.created_at) AS ultimo_click
            FROM clicks_afiliados c
            LEFT JOIN productos p ON p.id = c.producto_id
            GROUP BY p.id, p.nombre, p.plataforma_afiliado, c.plataforma
            ORDER BY clicks_total DESC, ultimo_click DESC
            LIMIT ?
            """
        rows = conn.execute(
            _sql(query),
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_clicks_afiliados_resumen():
    conn = get_connection()
    try:
        if USE_POSTGRES:
            query = """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN created_at::date = CURRENT_DATE THEN 1 ELSE 0 END) AS hoy,
                SUM(CASE WHEN created_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) AS ultimos_7_dias,
                COUNT(DISTINCT producto_id) AS productos_con_clicks
            FROM clicks_afiliados
            """
        else:
            query = """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN date(created_at) = date('now') THEN 1 ELSE 0 END) AS hoy,
                SUM(CASE WHEN created_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) AS ultimos_7_dias,
                COUNT(DISTINCT producto_id) AS productos_con_clicks
            FROM clicks_afiliados
            """
        row = conn.execute(_sql(query)).fetchone()
        return {
            "total": row["total"] or 0,
            "hoy": row["hoy"] or 0,
            "ultimos_7_dias": row["ultimos_7_dias"] or 0,
            "productos_con_clicks": row["productos_con_clicks"] or 0,
        }
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

class PedidoError(ValueError):
    pass


def _dinero(value):
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if not amount.is_finite() or amount <= 0:
        raise PedidoError("El producto no tiene un precio válido.")
    return amount


def crear_pedido(cliente_nombre, cliente_email, cliente_telefono,
                 cliente_direccion, total, items, checkout_key=None,
                 metodo_pago="transferencia", reserva_expira="",
                 zona_envio="", envio_costo=0,
                 cliente_entre_calles="", cliente_localidad="", cliente_codigo_postal=""):
    """Crea el pedido reservando stock en la misma transacción.

    El total se recalcula en el servidor (no se confía en el carrito de la
    sesión) sumando los subtotales actuales de los productos más el costo de
    envío. Usa bloqueo de filas y `checkout_key` para resolver pedidos
    duplicados o concurrentes en un único pedido.
    `metodo_pago` puede ser 'transferencia' o 'contra_entrega'. `reserva_expira`
    es un timestamp ('YYYY-MM-DD HH:MM:SS') tras el cual la reserva se libera
    automáticamente. `zona_envio`/`envio_costo` y los datos de dirección
    completan la entrega.
    Lanza PedidoError (subclase de ValueError) si algo no está disponible.
    """
    conn = get_connection()
    try:
        if not USE_POSTGRES:
            conn.execute("BEGIN IMMEDIATE")
        if checkout_key:
            if USE_POSTGRES:
                lock_id = int.from_bytes(hashlib.sha256(checkout_key.encode()).digest()[:8], "big", signed=True)
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
            existing = conn.execute(_sql("SELECT id FROM pedidos WHERE checkout_key = ?"), (checkout_key,)).fetchone()
            if existing:
                return existing["id"]
        if not items:
            raise PedidoError("El carrito está vacío.")
        try:
            envio = round(float(envio_costo or 0), 2)
        except (TypeError, ValueError):
            envio = 0.0
        if envio < 0:
            envio = 0.0
        checked = []
        seen = set()
        for item in sorted(items.values(), key=lambda i: int(i.get("producto_id") or 0)):
            product_id = int(item.get("producto_id") or 0)
            quantity = int(item.get("cantidad") or 0)
            if quantity < 1 or product_id in seen:
                raise PedidoError("El pedido tiene una cantidad inválida.")
            seen.add(product_id)
            query = "SELECT * FROM productos WHERE id = ?" + (" FOR UPDATE" if USE_POSTGRES else "")
            row = conn.execute(_sql(query), (product_id,)).fetchone()
            product = dict(row) if row else {}
            if (not product.get("activo") or not product.get("publicar") or product.get("es_afiliado")
                    or product.get("tipo_producto") in ("amazon_affiliate", "afiliado_digital")):
                raise PedidoError("Un producto del carrito ya no está disponible. Revisá el carrito.")
            price = _dinero(product.get("precio_venta") or 0)
            if item.get("precio") is not None and price != _dinero(item["precio"]):
                raise PedidoError("Cambió el precio de un producto. Revisá el carrito antes de confirmar.")
            if quantity > (product.get("stock") or 0):
                raise PedidoError(f"Stock insuficiente de '{product['nombre']}' (disponible: {product.get('stock') or 0}).")
            checked.append((product_id, product["nombre"], quantity, price))
        amount = sum((price * quantity for _, _, quantity, price in checked), Decimal("0"))
        total_calc = round(float(amount) + envio, 2)
        pedido_id = _insert_and_get_id(
            conn,
            """INSERT INTO pedidos
               (cliente_nombre, cliente_email, cliente_telefono, cliente_direccion,
                cliente_entre_calles, cliente_localidad, cliente_codigo_postal, total,
                metodo_pago, reserva_expira, zona_envio, envio_costo, stock_reservado, checkout_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (cliente_nombre, cliente_email, cliente_telefono, cliente_direccion,
             cliente_entre_calles or "", cliente_localidad or "", cliente_codigo_postal or "", total_calc,
             metodo_pago or "transferencia", reserva_expira or "", zona_envio or "", envio, checkout_key),
        )
        for product_id, name, quantity, price in checked:
            conn.execute(_sql("INSERT INTO pedido_items (pedido_id, producto_id, nombre, cantidad, precio_unitario, subtotal) VALUES (?, ?, ?, ?, ?, ?)"),
                         (pedido_id, product_id, name, quantity, float(price), float(price * quantity)))
            conn.execute(_sql("UPDATE productos SET stock = stock - ? WHERE id = ?"), (quantity, product_id))
        conn.commit()
        return pedido_id
    except IntegrityError:
        conn.rollback()
        if checkout_key:
            row = conn.execute(_sql("SELECT id FROM pedidos WHERE checkout_key = ?"), (checkout_key,)).fetchone()
            if row:
                return row["id"]
        raise
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


def actualizar_estado_pedido(pedido_id, estado):
    transitions = {
        "pendiente": {"confirmado", "pagado", "cancelado"},
        "confirmado": {"comprado", "pagado", "cancelado"},
        "comprado": {"pagado", "enviado", "cancelado"},
        "pagado": {"comprado", "enviado", "cancelado"},
        "enviado": {"entregado"},
        "entregado": set(), "cancelado": set(),
    }
    conn = get_connection()
    try:
        if not USE_POSTGRES:
            conn.execute("BEGIN IMMEDIATE")
        query = "SELECT * FROM pedidos WHERE id = ?" + (" FOR UPDATE" if USE_POSTGRES else "")
        row = conn.execute(_sql(query), (pedido_id,)).fetchone()
        if not row:
            raise PedidoError("Pedido no encontrado.")
        if estado == row["estado"]:
            return False
        if estado not in transitions.get(row["estado"], set()):
            raise PedidoError("Ese cambio de estado no está permitido.")
        reserved = row["stock_reservado"]
        if estado == "pagado" and not reserved:
            items = conn.execute(_sql("SELECT producto_id, cantidad FROM pedido_items WHERE pedido_id = ? ORDER BY producto_id"), (pedido_id,)).fetchall()
            for item in items:
                changed = conn.execute(_sql("UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?"),
                                       (item["cantidad"], item["producto_id"], item["cantidad"]))
                if changed.rowcount != 1:
                    raise PedidoError("Stock insuficiente para confirmar este pedido anterior. Revisá el inventario.")
            reserved = 1
        if estado == "cancelado" and reserved:
            items = conn.execute(_sql("SELECT producto_id, cantidad FROM pedido_items WHERE pedido_id = ? ORDER BY producto_id"), (pedido_id,)).fetchall()
            for item in items:
                conn.execute(_sql("UPDATE productos SET stock = stock + ? WHERE id = ?"), (item["cantidad"], item["producto_id"]))
            reserved = 0
        reserva = "" if estado == "cancelado" else (row["reserva_expira"] or "")
        conn.execute(_sql("UPDATE pedidos SET estado = ?, stock_reservado = ?, reserva_expira = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"),
                     (estado, reserved, reserva, pedido_id))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
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
    """Cancela un pedido y devuelve el stock reservado a los productos.

    Delega en `actualizar_estado_pedido` para respetar el flag `stock_reservado`
    y no devolver stock dos veces. No toca pedidos ya cancelados ni entregados.
    """
    conn = get_connection()
    try:
        pedido = conn.execute(
            _sql("SELECT estado FROM pedidos WHERE id = ?"), (pedido_id,)
        ).fetchone()
    finally:
        conn.close()
    if not pedido or pedido["estado"] in ("cancelado", "entregado"):
        return False
    try:
        return actualizar_estado_pedido(pedido_id, "cancelado")
    except PedidoError:
        return False


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
