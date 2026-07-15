import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import db as local_db
from db import DB_PATH

SEED_PATH = os.path.join(os.path.dirname(__file__), "data", "seed.json")


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
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
        DELETE FROM imagenes;
        DELETE FROM productos;
        DELETE FROM proveedores;
    """)


def seed_database(conn, data):
    for prov in data["proveedores"]:
        conn.execute(
            "INSERT INTO proveedores (id, nombre, contacto, notas, created_at) VALUES (?,?,?,?,?)",
            (
                prov["id"], prov["nombre"], prov.get("contacto", ""),
                prov.get("notas", ""), prov.get("created_at", ""),
            ),
        )

    for prod in data["productos"]:
        conn.execute(
            """INSERT INTO productos (id, nombre, descripcion, proveedor_id, costo, precio_venta,
               margen_porcentaje, iva_porcentaje, categoria, stock, activo, publicar, costo_usd,
               created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                prod["id"], prod["nombre"], prod.get("descripcion", ""),
                prod["proveedor_id"], prod["costo"], prod["precio_venta"],
                prod.get("margen_porcentaje", 0), prod.get("iva_porcentaje", 21),
                prod.get("categoria", ""), prod.get("stock", 1), prod.get("activo", 1),
                prod.get("publicar", 0), prod.get("costo_usd", 0),
                prod.get("created_at", ""), prod.get("updated_at", ""),
            ),
        )

    for img in data["imagenes"]:
        conn.execute(
            "INSERT INTO imagenes (id, producto_id, archivo, es_principal) VALUES (?,?,?,?)",
            (img["id"], img["producto_id"], img["archivo"], img.get("es_principal", 0)),
        )


def seed_from_file(seed_path, force=False):
    if not os.path.exists(seed_path):
        print("No seed.json found, skipping seed")
        return

    local_db.init_db()

    with open(seed_path, encoding="utf-8") as f:
        data = json.load(f)

    conn = local_db.get_connection()
    existing = conn.execute("SELECT COUNT(*) as c FROM productos").fetchone()
    current_count = existing["c"] if existing else 0

    if current_count > 0 and not force:
        print(f"DB already has {current_count} productos, skipping seed")
        conn.close()
        return

    if current_count > 0 and force:
        print("Force reseed enabled: clearing existing database data...")
        reset_data(conn)

    seed_database(conn, data)
    conn.commit()
    conn.close()
    print(
        f"Seeded: {len(data['proveedores'])} proveedores, {len(data['productos'])} productos, {len(data['imagenes'])} imagenes"
    )


if __name__ == "__main__":
    args = parse_args()
    seed_from_file(args.seed, force=args.force)
