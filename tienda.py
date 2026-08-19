"""Public shop: catalog, cart, checkout, bank transfer payment."""

import os
import re
import unicodedata
from datetime import datetime, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, abort,
)

import db
import config
import integraciones as itgr

tienda = Blueprint("tienda", __name__, template_folder="templates")

STORE_NAME = config.get("TIENDA_NOMBRE")
STORE_WA = config.get("TIENDA_WA")

# ─── Auditorio público: categorías por slug (ClickYa) ──────────────
GRUPOS_CATEGORIAS = {
    "tech": {
        "titulo": "Tech & Celulares",
        "subtitulo": "Smartphones, audio y accesorios de última generación.",
        "icono": "📱",
        "categorias": ["Celulares", "Audio", "Accesorios"],
    },
    "gadgets": {
        "titulo": "Gadgets & Accesorios",
        "subtitulo": "Accesorios, audio y wearables que simplifican tu día.",
        "icono": "⌚",
        "categorias": ["Accesorios", "Audio", "Celulares"],
    },
    "hogar-inteligente": {
        "titulo": "Hogar Inteligente",
        "subtitulo": "Electrodomésticos y calefacción para un hogar más cómodo.",
        "icono": "🏠",
        "categorias": ["Hogar", "Calefacción"],
    },
    "deportes": {
        "titulo": "Deportes & Fitness",
        "subtitulo": "Equipamiento para entrenar en casa sin excusas.",
        "icono": "💪",
        "categorias": ["Deportes"],
    },
}
NAV_CATEGORIAS = list(GRUPOS_CATEGORIAS)

_CSS_PATH = os.path.join(os.path.dirname(__file__), "static", "tienda.css")
CSS_VERSION = str(int(os.path.getmtime(_CSS_PATH))) if os.path.exists(_CSS_PATH) else "1"

CARRITO_KEY = "carrito"


def _get_carrito():
    return session.get(CARRITO_KEY, {})


def _save_carrito(data):
    session[CARRITO_KEY] = data
    session.modified = True


def _cant_carrito():
    return sum(i["cantidad"] for i in _get_carrito().values())


def _estimar_entrega():
    """Entrega según el momento del día (hora local):
    - Entre 12:00 AM y 11:59 AM (antes del mediodía) → 'hoy'
    - El resto del día → 'mañana'
    """
    ahora = datetime.now()
    if ahora.hour < 12:
        return "hoy"
    return "mañana"

DELIVERY_INFO = config.get("DELIVERY_INFO") or "Se entrega dentro de las 24 hs hábiles posteriores a la confirmación del pago."


@tienda.context_processor
def inject_globals():
    logo = config.get("TIENDA_LOGO") or config.get("TIENDA_NOMBRE")
    return {
        "wa_link": STORE_WA,
        "banco": config.get("BANCO"),
        "banco_titular": config.get("BANCO_TITULAR"),
        "banco_cbu": config.get("BANCO_CBU"),
        "banco_alias": config.get("BANCO_ALIAS"),
        "banco_tipo": config.get("BANCO_TIPO"),
        "banco_configurado": config.datos_bancarios_completos(),
        "tienda_logo": logo,
        "tienda_color": config.get("TIENDA_COLOR"),
        "tienda_descripcion": config.get("TIENDA_DESCRIPCION"),
        "delivery_info": DELIVERY_INFO,
        "entrega_estimada": _estimar_entrega(),
        "cant_carrito": _cant_carrito(),
        "public_url": (config.get("PUBLIC_URL") or "").rstrip("/"),
        "css_version": CSS_VERSION,
        "categorias": db.get_categorias(publicado_only=True),
        "nav_categorias": [
            {"slug": slug, **GRUPOS_CATEGORIAS[slug]} for slug in NAV_CATEGORIAS
        ],
        "origen_nav": ORIGEN_NAV,
        "origen_activa": request.args.get("origen", ""),
        "producto_beneficios": producto_beneficios,
        "producto_badge": producto_badge,
        "cta_producto": cta_producto,
        "producto_tipo_label": producto_tipo_label,
    }


# ─── Helpers de tipo de producto (local / digital / amazon) ────────

def _es_externo(p):
    """Un producto es externo si está marcado como afiliado o su tipo es digital/amazon."""
    return bool(p.get("es_afiliado")) or itgr.es_externo(p.get("tipo_producto"))


def producto_tipo_label(p):
    """Etiqueta corta del tipo de producto (para chips y cards)."""
    if _es_externo(p):
        tipo = p.get("tipo_producto")
        if tipo == "afiliado_digital":
            return "Curso / Digital"
        return "Importado Amazon"
    return "Stock Local (AMBA)"


def cta_producto(p):
    """Devuelve los datos del botón de compra según el tipo de producto."""
    tipo = p.get("tipo_producto")
    if _es_externo(p):
        url = itgr.producto_url_externa(p)
        plataforma = p.get("plataforma_afiliado") or itgr.detectar_plataforma(url or "")
        if tipo == "afiliado_digital" and plataforma == "hotmart":
            label, kicker = "Acceder al curso", "Curso digital de acceso inmediato"
        elif plataforma == "aliexpress":
            label, kicker = "Ver precio en AliExpress", "Precio actualizado en AliExpress"
        elif plataforma == "mercadolibre":
            label, kicker = "Ver oferta en Mercado Libre", "Precio actualizado en Mercado Libre"
        else:
            label, kicker = "Ver en Amazon", "Precio y envío calculados en Amazon"
        return {
            "url": url or url_for("tienda.producto", id=p["id"]),
            "label": label, "kicker": kicker, "externo": True,
            "tipo": tipo, "plataforma": plataforma,
        }
    return {
        "url": url_for("tienda.producto", id=p["id"]),
        "label": "Ver producto", "kicker": None, "externo": False,
        "tipo": tipo or "fisico_local", "plataforma": "",
    }


# ─── Helpers de card (afiliado/Amazon) ─────────────────────────────

def _norm_texto(s):
    """Normaliza texto: minúsculas y sin acentos (para comparar categorías)."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


def _segmentos_beneficios(nombre):
    """Extrae frases de beneficio del nombre del producto.

    Los nombres suelen venir con ' - ' o ' | ' separando features:
        'Smartwatch Serie 10 - Pantalla Infinita + Notificaciones y Llamadas'
    Se toman los fragmentos descriptivos (todo menos la marca/nombre base).
    """
    if not nombre:
        return []
    partes = re.split(r"\s*-\s*|\s*\|\s*", nombre)
    beneficios = []
    for i, parte in enumerate(partes):
        if i == 0:
            continue
        for frag in re.split(r"\s*\+\s*|\s*/\s*", parte):
            frag = frag.strip(" (),;•")
            if not frag:
                continue
            clave = _norm_texto(frag)
            if not any(_norm_texto(b) == clave for b in beneficios):
                beneficios.append(frag)
    return beneficios


def producto_beneficios(p, cantidad=3):
    """Devuelve una lista corta (3) de beneficios clave para la card.

    Prioridad: campo manual `beneficios` (1 por línea o separados por ' | ')
    → descripción curada (por línea) → inferido del nombre.
    Completa con propuestas de valor genéricas.
    """
    def _limpiar(lineas):
        out = []
        for l in lineas:
            l = l.strip(" -•\t·|").strip()
            if l:
                out.append(l)
        return out

    manual = (p.get("beneficios") or "").strip()
    if manual:
        lineas = []
        for parte in re.split(r"[|\n]", manual):
            lineas.extend(_limpiar([parte]))
        if lineas:
            return lineas[:cantidad]

    descripcion = (p.get("descripcion") or "").strip()
    if descripcion:
        lineas = _limpiar(descripcion.split("\n"))
        if len(lineas) >= cantidad:
            return lineas[:cantidad]

    ben = _segmentos_beneficios(p.get("nombre") or "")
    if _es_externo(p):
        extras = ["Compra 100% segura vía Amazon",
                  "Envío a Argentina disponible",
                  "Atención y soporte ClickYa"]
    else:
        extras = ["Stock disponible en AMBA",
                  "Entrega en 24 hs hábiles",
                  "Atención y soporte ClickYa"]
    i = 0
    while len(ben) < cantidad and i < len(extras):
        if extras[i] not in ben:
            ben.append(extras[i])
        i += 1
    return ben[:cantidad]


def producto_badge(p):
    """Etiqueta promocional de la card según categoría (solo prop, no canal).

    El canal (Local / Amazon Importado / Digital) se muestra aparte en el badge
    de tipo para no mezclar mensajes en la misma tarjeta.
    """
    cat = _norm_texto(p.get("categoria") or "")
    if cat in ("celulares", "deportes", "consolas"):
        return "Top Ventas"
    if cat in ("audio", "hogar", "calefacción", "calefaccion"):
        return "Recomendado"
    if cat in ("accesorios", "gadgets"):
        return "Nuevo Ingreso"
    return ""


def _pesos(val):
    if val is None:
        return "-"
    return f"$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _productos_con_imagen(productos):
    for p in productos:
        imgs = db.get_imagenes(p["id"])
        p["imagen"] = db.normalizar_imagen(imgs[0]["archivo"]) if imgs else None
    return productos


# ─── Landing / Link-in-bio ─────────────────────────────────────────

@tienda.route("/")
def index():
    """Raíz: redirige directo al catálogo (sin página de inicio)."""
    return redirect(url_for("tienda.catalogo"))


@tienda.route("/bio")
def bio():
    """Vista móvil estilo Link-in-bio, separada de la home (punto de entrada desde redes sociales)."""
    productos = _productos_publicados()
    _productos_con_imagen(productos)
    return render_template("tienda/bio.html",
                           store_name=STORE_NAME,
                           destacados=productos[:6],
                           total_productos=len(productos))


@tienda.route("/nosotros")
def nosotros():
    """Página institucional: quiénes somos, pilares y compromisos."""
    return render_template("tienda/nosotros.html", store_name=STORE_NAME)


# ─── Catálogo ──────────────────────────────────────────────────────

def _productos_publicados():
    productos = db.get_productos(publicado_only=True)
    return [p for p in productos
            if _es_externo(p) or (p.get("precio_venta") and p["precio_venta"] > 0)]


ORIGEN_LABELS = {
    "local": "Productos",
    "digital": "Cursos Digitales",
    "amazon": "Amazon Importados",
}

ORIGEN_NAV = [
    {"key": "local", "label": "Productos", "icono": "🚚"},
    {"key": "digital", "label": "Cursos Digitales", "icono": "💻"},
    {"key": "amazon", "label": "Amazon Importados", "icono": "📦"},
]


def _filtrar_origen(productos, origen):
    def tipo_de(p):
        tipo = p.get("tipo_producto")
        if tipo == "afiliado_digital" or (p.get("es_afiliado") and tipo != "amazon_affiliate"):
            return "digital"
        if tipo == "amazon_affiliate" or (p.get("es_afiliado") and p.get("plataforma_afiliado") == "amazon"):
            return "amazon"
        return "local"
    if not origen:
        return productos
    return [p for p in productos if tipo_de(p) == origen]


@tienda.route("/tienda")
def catalogo():
    cat = request.args.get("cat", "").strip()
    origen = request.args.get("origen", "").strip()
    productos = _productos_publicados()
    if cat:
        productos = [p for p in productos
                     if _norm_texto(p.get("categoria") or "") == _norm_texto(cat)]
    productos = _filtrar_origen(productos, origen)
    _productos_con_imagen(productos)
    return render_template("tienda/catalogo.html",
                           productos=productos,
                           store_name=STORE_NAME,
                           cat_activa="",
                           origen_activa=origen,
                           origen_labels=ORIGEN_LABELS,
                           grupo=None)


@tienda.route("/<slug>")
def categoria(slug):
    """Página de categoría destacada: /tech, /gadgets, /hogar-inteligente, /deportes."""
    grupo = GRUPOS_CATEGORIAS.get(slug)
    if not grupo:
        return redirect(url_for("tienda.catalogo"))
    cats = [_norm_texto(c) for c in grupo["categorias"]]
    productos = [
        p for p in _productos_publicados()
        if cats and _norm_texto(p.get("categoria") or "") in cats
    ]
    _productos_con_imagen(productos)
    return render_template("tienda/catalogo.html",
                           productos=productos,
                           store_name=STORE_NAME,
                           cat_activa=slug,
                           origen_activa="",
                           origen_labels=ORIGEN_LABELS,
                           grupo=grupo)


@tienda.route("/tienda/<int:id>")
def producto(id):
    p = db.get_producto(id)
    if not p or not (_es_externo(p)
                     or (p.get("precio_venta") and p["precio_venta"] > 0)):
        flash("Producto no disponible.", "error")
        return redirect(url_for("tienda.catalogo"))
    imgs = db.get_imagenes(id)
    for i, img in enumerate(imgs):
        imgs[i]["archivo"] = db.normalizar_imagen(img["archivo"])
    return render_template("tienda/producto.html",
                           p=p, imagenes=imgs,
                           store_name=STORE_NAME, peso=_pesos)


@tienda.route("/s/<int:id>")
def enlace_corto(id):
    """URL corta para compartir: redirige a la ficha del producto."""
    p = db.get_producto(id)
    if not p or not (_es_externo(p)
                     or (p.get("precio_venta") and p["precio_venta"] > 0)):
        abort(404)
    return redirect(url_for("tienda.producto", id=id))


# ─── Carrito ───────────────────────────────────────────────────────

@tienda.route("/carrito")
def ver_carrito():
    carrito = _get_carrito()
    total = sum(i["precio"] * i["cantidad"] for i in carrito.values())
    return render_template("tienda/carrito.html",
                           carrito=carrito, total=total,
                           store_name=STORE_NAME, peso=_pesos)


@tienda.route("/carrito/agregar/<int:id>", methods=["POST"])
def carrito_agregar(id):
    p = db.get_producto(id)
    if not p or not p.get("precio_venta") or p["precio_venta"] <= 0:
        flash("Producto no disponible.", "error")
        return redirect(url_for("tienda.catalogo"))
    if _es_externo(p):
        flash("Este producto se compra en la plataforma externa.", "error")
        return redirect(url_for("tienda.producto", id=id))

    cantidad = max(int(request.form.get("cantidad", 1)), 1)
    stock = p.get("stock") or 0
    if stock == 0:
        flash("Producto agotado.", "error")
        return redirect(url_for("tienda.producto", id=id))
    if cantidad > stock:
        flash(f"Stock insuficiente. Disponible: {stock}", "error")
        return redirect(url_for("tienda.producto", id=id))

    imgs = db.get_imagenes(id)
    carrito = _get_carrito()
    key = str(id)
    if key in carrito:
        nueva = carrito[key]["cantidad"] + cantidad
        carrito[key]["cantidad"] = min(nueva, stock) if stock > 0 else nueva
    else:
        carrito[key] = {
            "nombre": p["nombre"],
            "precio": p["precio_venta"],
            "cantidad": cantidad,
            "imagen": db.normalizar_imagen(imgs[0]["archivo"]) if imgs else None,
            "stock": stock,
            "producto_id": id,
        }
    _save_carrito(carrito)
    flash(f"{p['nombre']} agregado al carrito.", "success")
    return redirect(url_for("tienda.ver_carrito"))


@tienda.route("/carrito/actualizar/<int:id>", methods=["POST"])
def carrito_actualizar(id):
    cantidad = max(int(request.form.get("cantidad", 1)), 1)
    carrito = _get_carrito()
    key = str(id)
    if key in carrito:
        stock = carrito[key].get("stock", 0)
        if stock > 0:
            cantidad = min(cantidad, stock)
        carrito[key]["cantidad"] = cantidad
        _save_carrito(carrito)
    return redirect(url_for("tienda.ver_carrito"))


@tienda.route("/carrito/eliminar/<int:id>", methods=["POST"])
def carrito_eliminar(id):
    carrito = _get_carrito()
    carrito.pop(str(id), None)
    _save_carrito(carrito)
    return redirect(url_for("tienda.ver_carrito"))


@tienda.route("/comprar-ahora/<int:id>", methods=["POST"])
def comprar_ahora(id):
    p = db.get_producto(id)
    if not p or not p.get("precio_venta") or p["precio_venta"] <= 0:
        flash("Producto no disponible.", "error")
        return redirect(url_for("tienda.catalogo"))
    if _es_externo(p):
        flash("Este producto se compra en la plataforma externa.", "error")
        return redirect(url_for("tienda.producto", id=id))

    cantidad = max(int(request.form.get("cantidad", 1)), 1)
    stock = p.get("stock") or 0
    if stock == 0:
        flash("Producto agotado.", "error")
        return redirect(url_for("tienda.producto", id=id))
    if cantidad > stock:
        flash(f"Stock insuficiente. Disponible: {stock}", "error")
        return redirect(url_for("tienda.producto", id=id))

    imgs = db.get_imagenes(id)
    _save_carrito({str(id): {
        "nombre": p["nombre"],
        "precio": p["precio_venta"],
        "cantidad": cantidad,
        "imagen": db.normalizar_imagen(imgs[0]["archivo"]) if imgs else None,
        "stock": stock,
        "producto_id": id,
    }})
    return redirect(url_for("tienda.checkout"))


# ─── Checkout ──────────────────────────────────────────────────────

@tienda.route("/checkout")
def checkout():
    carrito = _get_carrito()
    if not carrito:
        flash("El carrito está vacío.", "error")
        return redirect(url_for("tienda.catalogo"))
    total = sum(i["precio"] * i["cantidad"] for i in carrito.values())
    return render_template("tienda/checkout.html",
                           carrito=carrito, total=total,
                           store_name=STORE_NAME, peso=_pesos)


@tienda.route("/checkout/procesar", methods=["POST"])
def checkout_procesar():
    carrito = _get_carrito()
    if not carrito:
        flash("El carrito está vacío.", "error")
        return redirect(url_for("tienda.catalogo"))

    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip()
    telefono = request.form.get("telefono", "").strip()
    direccion = request.form.get("direccion", "").strip()

    if not nombre or not email:
        flash("Completá nombre y email.", "error")
        return redirect(url_for("tienda.checkout"))

    total = sum(i["precio"] * i["cantidad"] for i in carrito.values())
    pedido_id = db.crear_pedido(nombre, email, telefono, direccion, total, carrito)

    _save_carrito({})

    return redirect(url_for("tienda.gracias", id=pedido_id))


# ─── Google Merchant Center XML Feed ─────────────────────────────

@tienda.route("/productos.xml")
def merchant_feed():
    productos = db.get_productos(publicado_only=True)
    productos = [p for p in productos if p.get("precio_venta") and p["precio_venta"] > 0]
    _productos_con_imagen(productos)

    from flask import Response
    from xml.sax.saxutils import escape

    items = []
    for p in productos:
        imgs = db.get_imagenes(p["id"])
        img = db.normalizar_imagen(imgs[0]["archivo"]) if imgs else ""
        if img and not img.startswith("http"):
            img = request.host_url.rstrip("/") + "/" + img
        link = url_for("tienda.producto", id=p["id"], _external=True)
        desc = escape((p.get("descripcion") or p["nombre"])[:5000])
        name = escape(p["nombre"][:150])
        items.append(f"""    <item>
      <g:id>{p['id']}</g:id>
      <g:title>{name}</g:title>
      <g:description>{desc}</g:description>
      <g:link>{escape(link)}</g:link>
      <g:image_link>{escape(img)}</g:image_link>
      <g:availability>{'in_stock' if p.get('stock', 0) > 0 else 'out_of_stock'}</g:availability>
      <g:price>{p['precio_venta']:.2f} ARS</g:price>
      <g:condition>new</g:condition>
      <g:brand>{escape(STORE_NAME)}</g:brand>
    </item>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:g="http://base.google.com/ns/1.0" version="2.0">
  <channel>
    <title>{escape(STORE_NAME)}</title>
    <link>{request.host_url}</link>
    <description>{escape(STORE_NAME)} - Productos</description>
{chr(10).join(items)}
  </channel>
</rss>"""
    return Response(xml, mimetype="application/xml; charset=utf-8")


# ─── Confirmación ──────────────────────────────────────────────────

@tienda.route("/gracias/<int:id>")
def gracias(id):
    pedido = db.get_pedido(id)
    if not pedido:
        flash("Pedido no encontrado.", "error")
        return redirect(url_for("tienda.catalogo"))
    line_items = db.get_pedido_items(id)
    pedido["line_items"] = line_items

    return render_template("tienda/gracias.html",
                           pedido=pedido,
                           store_name=STORE_NAME,
                           wa_link=STORE_WA,
                           peso=_pesos)



