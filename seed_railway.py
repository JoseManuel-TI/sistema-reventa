import json, os, sys

sys.path.insert(0, os.path.dirname(__file__))

import db as local_db
from db import DB_PATH

SEED_PATH = os.path.join(os.path.dirname(__file__), "data", "seed.json")

if not os.path.exists(SEED_PATH):
    print("No seed.json found, skipping seed")
    exit(0)

# Initialize DB tables
local_db.init_db()

with open(SEED_PATH, encoding="utf-8") as f:
    data = json.load(f)

conn = local_db.get_connection()

# Only seed if DB is empty (non-destructive)
existing = conn.execute("SELECT COUNT(*) as c FROM productos").fetchone()
if existing and existing["c"] > 0:
    print(f"DB already has {existing['c']} productos, skipping seed")
    conn.close()
    exit(0)

conn.execute("PRAGMA foreign_keys = OFF")
conn.executescript("""
    DELETE FROM imagenes;
    DELETE FROM productos;
    DELETE FROM proveedores;
""")

for prov in data["proveedores"]:
    conn.execute(
        "INSERT INTO proveedores (id, nombre, contacto, notas, created_at) VALUES (?,?,?,?,?)",
        (prov["id"], prov["nombre"], prov.get("contacto",""), prov.get("notas",""), prov.get("created_at",""))
    )

for prod in data["productos"]:
    conn.execute(
        """INSERT INTO productos (id, nombre, descripcion, proveedor_id, costo, precio_venta,
           margen_porcentaje, iva_porcentaje, categoria, stock, activo, publicar, costo_usd,
           created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (prod["id"], prod["nombre"], prod.get("descripcion",""), prod["proveedor_id"],
         prod["costo"], prod["precio_venta"], prod.get("margen_porcentaje",0),
         prod.get("iva_porcentaje",21), prod.get("categoria",""), prod.get("stock",1),
         prod.get("activo",1), prod.get("publicar",0), prod.get("costo_usd",0),
         prod.get("created_at",""), prod.get("updated_at",""))
    )

for img in data["imagenes"]:
    conn.execute(
        "INSERT INTO imagenes (id, producto_id, archivo, es_principal) VALUES (?,?,?,?)",
        (img["id"], img["producto_id"], img["archivo"], img.get("es_principal",0))
    )

conn.commit()
conn.close()
print(f"Seeded: {len(data['proveedores'])} proveedores, {len(data['productos'])} productos, {len(data['imagenes'])} imagenes")
