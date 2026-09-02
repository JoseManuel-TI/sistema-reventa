"""
Seed the database from data/seed.json.
Works with both SQLite and PostgreSQL (auto-detected via db.USE_POSTGRES).
"""

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))

import db as local_db

SEED_PATH = os.path.join(os.path.dirname(__file__), "data", "seed.json")
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.environ.get("APP_DATA_DIR")
if not DATA_DIR and os.environ.get("RAILWAY_ENVIRONMENT"):
    DATA_DIR = "/data"
DATA_DIR = DATA_DIR or os.path.join(BASE_DIR, "data")
IMAGES_DIR = os.environ.get("IMAGES_DIR") or (
    os.path.join(DATA_DIR, "imagenes")
    if os.environ.get("RAILWAY_ENVIRONMENT")
    else os.path.join(BASE_DIR, "imagenes")
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed the local database from data/seed.json"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force reseed by clearing existing product data",
    )
    parser.add_argument(
        "--seed",
        default=SEED_PATH,
        help="Path to the seed JSON file",
    )
    return parser.parse_args()


def reset_data(conn):
    conn.execute("DELETE FROM imagenes")
    conn.execute("DELETE FROM productos")
    conn.execute("DELETE FROM proveedores")
    if local_db.USE_POSTGRES:
        conn.execute("ALTER SEQUENCE proveedores_id_seq RESTART WITH 1")
        conn.execute("ALTER SEQUENCE productos_id_seq RESTART WITH 1")
        conn.execute("ALTER SEQUENCE imagenes_id_seq RESTART WITH 1")


def seed_database(conn, data):
    for prov in data["proveedores"]:
        local_db.execute(
            conn,
            "INSERT INTO proveedores (id, nombre, contacto, notas, created_at) VALUES (?,?,?,?,?)",
            (prov["id"], prov["nombre"], prov.get("contacto", ""),
             prov.get("notas", ""), prov.get("created_at", "")),
        )

    for prod in data["productos"]:
        local_db.execute(
            conn,
            """INSERT INTO productos (id, nombre, descripcion, proveedor_id, costo, precio_venta,
               margen_porcentaje, iva_porcentaje, categoria, stock, activo, publicar, costo_usd,
               es_afiliado, link_afiliado, plataforma_afiliado, tipo_producto, moneda, external_url,
               beneficios, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (prod["id"], prod["nombre"], prod.get("descripcion", ""),
             prod["proveedor_id"], prod["costo"], prod["precio_venta"],
             prod.get("margen_porcentaje", 0), prod.get("iva_porcentaje", 21),
             prod.get("categoria", ""), prod.get("stock", 1), prod.get("activo", 1),
             prod.get("publicar", 0), prod.get("costo_usd", 0),
             prod.get("es_afiliado", 0), prod.get("link_afiliado", ""),
             prod.get("plataforma_afiliado", "amazon"), prod.get("tipo_producto", "fisico_local"),
             prod.get("moneda", "ARS"), prod.get("external_url", ""),
             prod.get("beneficios", ""),
             prod.get("created_at", ""), prod.get("updated_at", "")),
        )

    for img in data["imagenes"]:
        local_db.execute(
            conn,
            "INSERT INTO imagenes (id, producto_id, archivo, es_principal) VALUES (?,?,?,?)",
            (img["id"], img["producto_id"], img["archivo"], img.get("es_principal", 0)),
        )

    if local_db.USE_POSTGRES:
        conn.execute("SELECT setval('proveedores_id_seq', (SELECT COALESCE(MAX(id), 1) FROM proveedores))")
        conn.execute("SELECT setval('productos_id_seq', (SELECT COALESCE(MAX(id), 1) FROM productos))")
        conn.execute("SELECT setval('imagenes_id_seq', (SELECT COALESCE(MAX(id), 1) FROM imagenes))")


def _provider_id_by_name(conn, nombre):
    row = local_db.execute(conn, "SELECT id FROM proveedores WHERE nombre = ?", (nombre,)).fetchone()
    return row["id"] if row else None


def _ensure_provider(conn, prov):
    existing_id = _provider_id_by_name(conn, prov["nombre"])
    if existing_id:
        return existing_id
    local_db.execute(
        conn,
        "INSERT INTO proveedores (nombre, contacto, notas) VALUES (?,?,?)",
        (prov["nombre"], prov.get("contacto", ""), prov.get("notas", "")),
    )
    return _provider_id_by_name(conn, prov["nombre"])


def _seed_affiliate_products(conn, data):
    """Inserta o actualiza afiliados sin tocar los productos locales existentes."""
    proveedores = {p["id"]: p for p in data.get("proveedores", [])}
    afiliados = [
        p for p in data.get("productos", [])
        if p.get("es_afiliado") or p.get("tipo_producto") in ("amazon_affiliate", "afiliado_digital")
    ]
    if not afiliados:
        return 0, 0

    creados = 0
    actualizados = 0
    id_map = {}
    for prod in afiliados:
        prov = proveedores.get(prod["proveedor_id"])
        proveedor_id = _ensure_provider(conn, prov) if prov else prod["proveedor_id"]
        destino = prod.get("external_url") or prod.get("link_afiliado") or ""
        row = None
        if destino:
            row = local_db.execute(
                conn,
                "SELECT id FROM productos WHERE external_url = ? OR link_afiliado = ?",
                (destino, destino),
            ).fetchone()
        if not row:
            row = local_db.execute(
                conn,
                "SELECT id FROM productos WHERE nombre = ?",
                (prod["nombre"],),
            ).fetchone()

        values = (
            prod["nombre"], prod.get("descripcion", ""), proveedor_id,
            prod.get("costo", 0), prod.get("precio_venta", 0),
            prod.get("margen_porcentaje", 0), prod.get("iva_porcentaje", 21),
            prod.get("categoria", ""), prod.get("stock", 0),
            prod.get("activo", 1), prod.get("publicar", 1),
            prod.get("costo_usd", 0), prod.get("es_afiliado", 1),
            prod.get("link_afiliado", ""), prod.get("plataforma_afiliado", "amazon"),
            prod.get("tipo_producto", "amazon_affiliate"), prod.get("moneda", "USD"),
            prod.get("external_url", destino), prod.get("beneficios", ""),
        )
        if row:
            local_db.execute(
                conn,
                """UPDATE productos SET
                   nombre=?, descripcion=?, proveedor_id=?, costo=?, precio_venta=?,
                   margen_porcentaje=?, iva_porcentaje=?, categoria=?, stock=?,
                   activo=?, publicar=?, costo_usd=?, es_afiliado=?, link_afiliado=?,
                   plataforma_afiliado=?, tipo_producto=?, moneda=?, external_url=?,
                   beneficios=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                values + (row["id"],),
            )
            product_id = row["id"]
            actualizados += 1
        else:
            local_db.execute(
                conn,
                """INSERT INTO productos
                   (nombre, descripcion, proveedor_id, costo, precio_venta,
                    margen_porcentaje, iva_porcentaje, categoria, stock, activo, publicar,
                    costo_usd, es_afiliado, link_afiliado, plataforma_afiliado,
                    tipo_producto, moneda, external_url, beneficios)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            row = local_db.execute(
                conn,
                "SELECT id FROM productos WHERE external_url = ? OR link_afiliado = ?",
                (destino, destino),
            ).fetchone()
            product_id = row["id"]
            creados += 1
        id_map[prod["id"]] = product_id

    for img in data.get("imagenes", []):
        old_product_id = img.get("producto_id")
        if old_product_id not in id_map:
            continue
        product_id = id_map[old_product_id]
        archivo = img["archivo"]
        exists = local_db.execute(
            conn,
            "SELECT id FROM imagenes WHERE producto_id = ? AND archivo = ?",
            (product_id, archivo),
        ).fetchone()
        if exists:
            continue
        local_db.execute(
            conn,
            "INSERT INTO imagenes (producto_id, archivo, es_principal) VALUES (?,?,?)",
            (product_id, archivo, img.get("es_principal", 1)),
        )

    return creados, actualizados


def copy_seed_images(data):
    for img in data.get("imagenes", []):
        archivo = img.get("archivo", "")
        if not archivo.startswith("imagenes/"):
            continue
        source = os.path.join(BASE_DIR, archivo)
        target = os.path.join(IMAGES_DIR, archivo[len("imagenes/"):])
        if not os.path.exists(source) or os.path.exists(target):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)


def seed_from_file(seed_path, force=False):
    if not os.path.exists(seed_path):
        print("No seed.json found, skipping seed")
        return

    local_db.init_db()

    with open(seed_path, encoding="utf-8") as f:
        data = json.load(f)

    copy_seed_images(data)

    conn = local_db.get_connection()
    try:
        cur = local_db.execute(conn, "SELECT COUNT(*) as c FROM productos")
        existing = cur.fetchone()
        current_count = existing["c"] if existing else 0

        if current_count > 0 and not force:
            creados, actualizados = _seed_affiliate_products(conn, data)
            conn.commit()
            print(
                f"DB already has {current_count} productos; affiliate sync: {creados} creados, {actualizados} actualizados"
            )
            return

        if current_count > 0 and force:
            print("Force reseed enabled: clearing existing database data...")
            reset_data(conn)

        seed_database(conn, data)
        conn.commit()
        print(
            f"Seeded: {len(data['proveedores'])} proveedores, {len(data['productos'])} productos, {len(data['imagenes'])} imagenes"
        )
    except Exception as e:
        conn.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    args = parse_args()
    seed_from_file(args.seed, force=args.force)
