"""Public shop: catalog, cart, checkout, bank transfer payment."""

import os
from datetime import datetime, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, abort,
)

import db
import config

tienda = Blueprint("tienda", __name__, template_folder="templates")

STORE_NAME = config.get("TIENDA_NOMBRE")
STORE_WA = config.get("TIENDA_WA")

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


def _estimar_entrega(hora_corte=14):
    """Calcula fecha estimada con corte a las 2 PM.
    Antes de las 2 PM en día hábil → hoy.
    Después de las 2 PM o fin de semana → próximo día hábil.
    """
    ahora = datetime.now()
    if ahora.hour < hora_corte and ahora.weekday() < 5:
        return "hoy"
    habiles = 0
    d = ahora
    while habiles < 1:
        d += timedelta(days=1)
        if d.weekday() < 5:
            habiles += 1
    return d.strftime("%d/%m")

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
    }


def _pesos(val):
    if val is None:
        return "-"
    return f"$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _productos_con_imagen(productos):
    for p in productos:
        imgs = db.get_imagenes(p["id"])
        p["imagen"] = imgs[0]["archivo"] if imgs else None
    return productos


# ─── Catálogo ──────────────────────────────────────────────────────

@tienda.route("/tienda")
def catalogo():
    import unicodedata
    cat = request.args.get("cat", "").strip()

    def _norm(s):
        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

    productos = db.get_productos(publicado_only=True)
    productos = [p for p in productos
                 if p.get("es_afiliado") or (p.get("precio_venta") and p["precio_venta"] > 0)]
    if cat:
        productos = [p for p in productos
                     if _norm(p.get("categoria") or "") == _norm(cat)]
    _productos_con_imagen(productos)
    return render_template("tienda/catalogo.html",
                           productos=productos,
                           store_name=STORE_NAME,
                           cat_activa=cat)


@tienda.route("/tienda/<int:id>")
def producto(id):
    p = db.get_producto(id)
    if not p or not (p.get("es_afiliado")
                     or (p.get("precio_venta") and p["precio_venta"] > 0)):
        flash("Producto no disponible.", "error")
        return redirect(url_for("tienda.catalogo"))
    imgs = db.get_imagenes(id)
    return render_template("tienda/producto.html",
                           p=p, imagenes=imgs,
                           store_name=STORE_NAME, peso=_pesos)


@tienda.route("/s/<int:id>")
def enlace_corto(id):
    """URL corta para compartir: redirige a la ficha del producto."""
    p = db.get_producto(id)
    if not p or not (p.get("es_afiliado")
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
            "imagen": imgs[0]["archivo"] if imgs else None,
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
        "imagen": imgs[0]["archivo"] if imgs else None,
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
        img = imgs[0]["archivo"] if imgs else ""
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



