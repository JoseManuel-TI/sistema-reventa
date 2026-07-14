"""
Exporta productos a distintos formatos:
- CSV para Mercado Libre (bulk upload)
- HTML para catálogo web
- HTML tarjetas 9:16 para Instagram (captura de pantalla → post)
- JSON (respaldo/portabilidad)
"""

import csv
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


def _preparar_productos(productos):
    """Agrega la imagen principal a cada producto."""
    from db import get_imagenes
    for p in productos:
        imgs = get_imagenes(p["id"])
        p["imagen_principal"] = imgs[0]["archivo"] if imgs else ""
    return productos


# ─── Mercado Libre ────────────────────────────────────────────────

def exportar_mercadolibre_csv(productos, nombre_archivo=None):
    """
    Genera CSV compatible con carga masiva de Mercado Libre.
    Columnas: título, precio, condición, listing_type_id, descripción,
              category_id, available_quantity, pictures.
    """
    if not nombre_archivo:
        fecha = datetime.now().strftime("%Y%m%d_%H%M")
        nombre_archivo = f"mercadolibre_{fecha}.csv"

    ruta = os.path.join(EXPORTS_DIR, nombre_archivo)
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    productos = _preparar_productos(productos)
    campos = [
        "TITULO", "PRECIO", "CONDICION", "LISTING_TYPE_ID",
        "DESCRIPCION", "CATEGORY_ID", "AVAILABLE_QUANTITY", "PICTURES",
    ]
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for p in productos:
            writer.writerow({
                "TITULO": p["nombre"],
                "PRECIO": p.get("precio_venta") or "",
                "CONDICION": "new",
                "LISTING_TYPE_ID": "gold_special",
                "DESCRIPCION": p.get("descripcion") or "",
                "CATEGORY_ID": "",
                "AVAILABLE_QUANTITY": p.get("stock") or 1,
                "PICTURES": p.get("imagen_principal") or "",
            })
    return ruta


# ─── Catálogo HTML ────────────────────────────────────────────────

def exportar_catalogo_html(productos, nombre_archivo=None):
    if not nombre_archivo:
        fecha = datetime.now().strftime("%Y%m%d_%H%M")
        nombre_archivo = f"catalogo_{fecha}.html"

    ruta = os.path.join(EXPORTS_DIR, nombre_archivo)
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    productos = _preparar_productos(productos)

    template_path = os.path.join(TEMPLATES_DIR, "catalogo.html")
    if os.path.exists(template_path):
        with open(template_path, encoding="utf-8") as f:
            template = f.read()
    else:
        template = _catalogo_default_template()

    tarjetas = ""
    for p in productos:
        img = p.get("imagen_principal") or ""
        precio = f"$ {p.get('precio_venta'):,.2f}".replace(",", ".") if p.get("precio_venta") else "Consultar"
        tarjetas += f"""
        <div class="card">
            {"<img src='{}' alt='{}'>".format(img, p["nombre"]) if img else "<div class='sin-imagen'>Sin imagen</div>"}
            <h3>{p['nombre']}</h3>
            <p class="descripcion">{p.get('descripcion', '')}</p>
            <p class="precio">{precio}</p>
            <p class="proveedor">{p.get('proveedor_nombre', '')}</p>
        </div>
        """

    # Use an HTML comment marker in the template to avoid accidental Jinja
    # parsing when templates are processed via Flask. Replace that marker
    # with the generated cards HTML.
    html = template.replace("<!--TARJETAS-->", tarjetas)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)
    return ruta


def _catalogo_default_template():
    return """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Catálogo</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#f5f5f5; padding:20px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:20px; max-width:1200px; margin:0 auto; }
.card { background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08); }
.card img { width:100%; height:280px; object-fit:cover; }
.sin-imagen { width:100%; height:280px; background:#eee; display:flex; align-items:center; justify-content:center; color:#999; }
.card h3 { padding:12px 16px 4px; font-size:16px; }
.descripcion { padding:0 16px; font-size:13px; color:#666; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.precio { padding:8px 16px 4px; font-size:20px; font-weight:700; color:#00a650; }
.proveedor { padding:4px 16px 12px; font-size:12px; color:#999; }
</style>
</head>
<body>
<div class="grid">{{TARJETAS}}</div>
</body>
</html>"""


# ─── Instagram 9:16 ───────────────────────────────────────────────

def exportar_instagram_html(productos, nombre_archivo=None):
    """
    Genera un HTML con tarjetas en formato 9:16 (1080x1920).
    Ideal para capturar pantalla y subir a Instagram / WhatsApp.
    """
    if not nombre_archivo:
        fecha = datetime.now().strftime("%Y%m%d_%H%M")
        nombre_archivo = f"instagram_{fecha}.html"

    ruta = os.path.join(EXPORTS_DIR, nombre_archivo)
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    productos = _preparar_productos(productos)

    template_path = os.path.join(TEMPLATES_DIR, "instagram_card.html")
    if os.path.exists(template_path):
        with open(template_path, encoding="utf-8") as f:
            template = f.read()
    else:
        template = _instagram_default_template()

    tarjetas = ""
    for p in productos:
        img = p.get("imagen_principal") or ""
        desc = p.get("descripcion", "")[:120]
        precio = f"$ {p.get('precio_venta'):,.2f}".replace(",", ".") if p.get("precio_venta") else "Consultar"
        card = template
        card = card.replace("{{IMAGEN}}", img)
        card = card.replace("{{NOMBRE}}", p["nombre"])
        card = card.replace("{{DESCRIPCION}}", desc)
        card = card.replace("{{PRECIO}}", precio)
        tarjetas += card + "\n"

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Instagram Posts</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#111; display:flex; flex-direction:column; align-items:center; padding:20px; }}
.tarjeta {{ width:540px; height:960px; background:#fff; border-radius:20px; overflow:hidden;
           margin-bottom:30px; position:relative; box-shadow:0 0 30px rgba(0,0,0,0.3); font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
.tarjeta img {{ width:100%; height:540px; object-fit:cover; }}
.tarjeta h2 {{ padding:20px 20px 8px; font-size:22px; }}
.tarjeta .desc {{ padding:0 20px; font-size:15px; color:#555; }}
.tarjeta .precio {{ padding:15px 20px; font-size:32px; font-weight:800; color:#00a650; }}
.tarjeta .cta {{ display:block; margin:10px 20px; padding:14px; background:#25D366; color:#fff;
                text-align:center; border-radius:30px; font-weight:700; font-size:18px; text-decoration:none; }}
.tarjeta .watermark {{ position:absolute; bottom:15px; right:20px; font-size:11px; color:#bbb; }}
</style>
</head>
<body>{tarjetas}</body>
</html>"""
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)
    return ruta


def _instagram_default_template():
    return """
<div class="tarjeta">
    <img src="{{IMAGEN}}" alt="{{NOMBRE}}">
    <h2>{{NOMBRE}}</h2>
    <p class="desc">{{DESCRIPCION}}</p>
    <p class="precio">{{PRECIO}}</p>
    <a class="cta" href="https://wa.me/5411XXXXXXXX?text=Hola%2C+quiero+{{NOMBRE}}">Consultar por WhatsApp</a>
    <div class="watermark">@tunegocio</div>
</div>"""


# ─── JSON ─────────────────────────────────────────────────────────

def exportar_json(productos, nombre_archivo=None):
    if not nombre_archivo:
        fecha = datetime.now().strftime("%Y%m%d_%H%M")
        nombre_archivo = f"productos_{fecha}.json"

    ruta = os.path.join(EXPORTS_DIR, nombre_archivo)
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    productos = _preparar_productos(productos)
    data = []
    for p in productos:
        data.append({
            "id": p["id"],
            "nombre": p["nombre"],
            "descripcion": p.get("descripcion"),
            "proveedor": p.get("proveedor_nombre"),
            "costo": p.get("costo"),
            "precio_venta": p.get("precio_venta"),
            "categoria": p.get("categoria"),
            "stock": p.get("stock"),
            "imagen": p.get("imagen_principal"),
        })

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return ruta
