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
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

_env_exports = os.environ.get("EXPORTS_DIR")
if _env_exports:
    EXPORTS_DIR = _env_exports
elif os.environ.get("RAILWAY_ENVIRONMENT"):
    EXPORTS_DIR = os.path.join("/data", "exports")
else:
    EXPORTS_DIR = os.path.join(BASE_DIR, "exports")


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
        pv = p.get("precio_venta")
        precio = f"$ {pv:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pv else "Consultar"
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

def exportar_instagram_html(productos, nombre_archivo=None, base_url="https://clickya.net"):
    """
    Genera un HTML con tarjetas en formato 9:16 (1080x1920).
    Ideal para capturar pantalla y subir a Instagram / WhatsApp.
    """
    from config import get as cfg_get
    import integraciones as itgr
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

    wa_link = cfg_get("TIENDA_WA") or "https://wa.me/5491126268359"
    tarjetas = ""
    for p in productos:
        img = p.get("imagen_principal") or ""
        if img and not img.startswith(("http://", "https://")):
            if base_url:
                img = f"{base_url.rstrip('/')}/{img.lstrip('/')}"
            else:
                img = img.lstrip("/")
        desc = p.get("descripcion", "")[:120]

        es_ext = itgr.es_externo(p.get("tipo_producto")) or bool(p.get("es_afiliado"))
        if es_ext:
            url_ext = itgr.producto_url_externa(p)
            tracking_url = f"{base_url.rstrip('/')}/out/{p['id']}?src=instagram_card" if base_url and url_ext else url_ext
            plataforma = p.get("plataforma_afiliado") or itgr.detectar_plataforma(url_ext or "")
            if p.get("tipo_producto") == "afiliado_digital" and plataforma == "hotmart":
                cta_label, cta_link, cta_wa = "🎓 Acceder al curso", tracking_url or wa_link, tracking_url or wa_link
                tipo_badge = "CURSO DIGITAL"
            elif plataforma == "aliexpress":
                cta_label, cta_link, cta_wa = "Ver precio en AliExpress", tracking_url or wa_link, tracking_url or wa_link
                tipo_badge = "IMPORTADO"
            elif plataforma == "mercadolibre":
                cta_label, cta_link, cta_wa = "Ver oferta en Mercado Libre", tracking_url or wa_link, tracking_url or wa_link
                tipo_badge = "OFERTA ML"
            else:
                cta_label, cta_link, cta_wa = "🛒 Ver precio en Amazon", tracking_url or wa_link, tracking_url or wa_link
                tipo_badge = "IMPORTADO AMAZON"
            precio = "Consultar precio"
            cta_clase = "cta amazon"
        else:
            pv = p.get("precio_venta")
            precio = f"$ {pv:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if pv else "Consultar"
            cta_label = "Comprar por WhatsApp"
            cta_link = f"{wa_link}?text=Hola%2C+quiero+{p['nombre'].replace(' ', '%20')}"
            cta_wa = wa_link
            tipo_badge = "STOCK LOCAL (AMBA)"
            cta_clase = "cta"

        card = template
        card = card.replace("{{IMAGEN}}", img)
        card = card.replace("{{NOMBRE}}", p["nombre"])
        card = card.replace("{{NOMBRE_WA}}", p["nombre"].replace(" ", "%20"))
        card = card.replace("{{DESCRIPCION}}", desc)
        card = card.replace("{{PRECIO}}", precio)
        card = card.replace("{{WA_LINK}}", wa_link)
        card = card.replace("{{TIPO_BADGE}}", tipo_badge)
        card = card.replace("{{CTA_LABEL}}", cta_label)
        card = card.replace("{{CTA_LINK}}", cta_link)
        card = card.replace("{{CTA_CLASS}}", cta_clase)
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
.tarjeta .cta.amazon {{ background:#ff9900; color:#232f3e; }}
.tarjeta .badge {{ position:absolute; top:16px; left:16px; background:#232f3e; color:#ff9900;
                  padding:6px 12px; border-radius:20px; font-size:12px; font-weight:800; letter-spacing:.5px; }}
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
    <span class="badge">{{TIPO_BADGE}}</span>
    <img src="{{IMAGEN}}" alt="{{NOMBRE}}">
    <h2>{{NOMBRE}}</h2>
    <p class="desc">{{DESCRIPCION}}</p>
    <p class="precio">{{PRECIO}}</p>
    <a class="{{CTA_CLASS}}" href="{{CTA_LINK}}" target="_blank">{{CTA_LABEL}}</a>
    <div class="watermark">@clickya.ar</div>
</div>"""


# ─── WhatsApp Business (Catálogo) ─────────────────────────────────

def exportar_whatsapp_csv(productos, nombre_archivo=None, base_url=""):
    """
    Genera CSV compatible con la carga masiva de catálogo de
    WhatsApp Business / Meta Commerce Manager.
    Columnas: title, description, link, image_link, price, currency, availability.
    Solo productos locales (físicos) con precio definido.
    """
    import integraciones as itgr
    if not nombre_archivo:
        fecha = datetime.now().strftime("%Y%m%d_%H%M")
        nombre_archivo = f"whatsapp_{fecha}.csv"

    ruta = os.path.join(EXPORTS_DIR, nombre_archivo)
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    productos = [p for p in _preparar_productos(productos)
                 if not itgr.es_externo(p.get("tipo_producto"))
                 and not p.get("es_afiliado")
                 and (p.get("precio_venta") or 0) > 0]

    campos = ["title", "description", "link", "image_link", "price", "currency", "availability"]
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for p in productos:
            img = p.get("imagen_principal") or ""
            if img and not img.startswith(("http://", "https://")):
                img = f"{base_url.rstrip('/')}/{img.lstrip('/')}" if base_url else ""
            link = p.get("link_catalogo") or ""
            writer.writerow({
                "title": p["nombre"],
                "description": (p.get("descripcion") or "")[:1000],
                "link": link,
                "image_link": img,
                "price": f"{p['precio_venta']:.2f}",
                "currency": "ARS",
                "availability": "in stock",
            })
    return ruta


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
