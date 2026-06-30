"""Public shop: catalog, cart, checkout, bank transfer payment."""

from datetime import datetime, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session,
)

import db
import config

tienda = Blueprint("tienda", __name__, template_folder="templates")

STORE_NAME = config.get("TIENDA_NOMBRE")
STORE_WA = config.get("TIENDA_WA")

CARRITO_KEY = "carrito"


def _get_carrito():
    return session.get(CARRITO_KEY, {})


def _save_carrito(data):
    session[CARRITO_KEY] = data
    session.modified = True


def _cant_carrito():
    return sum(i["cantidad"] for i in _get_carrito().values())


def _estimar_entrega():
    """Calcula fecha estimada: 24 hs hábiles desde hoy."""
    hoy = datetime.now()
    habiles = 0
    d = hoy
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
    productos = db.get_productos(publicado_only=True)
    productos = [p for p in productos
                 if p.get("precio_venta") and p["precio_venta"] > 0]
    _productos_con_imagen(productos)
    return render_template("tienda/catalogo.html",
                           productos=productos,
                           store_name=STORE_NAME)


@tienda.route("/tienda/<int:id>")
def producto(id):
    p = db.get_producto(id)
    if not p or not p.get("precio_venta") or p["precio_venta"] <= 0:
        flash("Producto no disponible.", "error")
        return redirect(url_for("tienda.catalogo"))
    imgs = db.get_imagenes(id)
    return render_template("tienda/producto.html",
                           p=p, imagenes=imgs,
                           store_name=STORE_NAME, peso=_pesos)


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
    if stock > 0 and cantidad > stock:
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
    if stock > 0 and cantidad > stock:
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



