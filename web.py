"""
Web UI - Flask server para gestionar el negocio de reventa.

Uso:
    python3 web.py
    # Abrir http://localhost:5000
"""

import os
import shutil
import traceback
import logging
from functools import wraps

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

import db
import config
import precios as pcalc
import importar_whatsapp
import exportar
from tienda import tienda
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, session,
)
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(__file__)
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))
app.secret_key = os.environ.get("SESSION_SECRET") or os.urandom(24).hex()
app.register_blueprint(tienda)

IMAGENES_DIR = os.path.join(BASE_DIR, "imagenes")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")


# ─── Auth ─────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        admin_pass = config.get("ADMIN_PASSWORD")
        if not admin_pass:
            flash("ADMIN_PASSWORD no configurada. Configurala via ADMIN_PASSWORD env var o data/config.json", "error")
        elif password == admin_pass:
            session["admin"] = True
            next_page = request.args.get("next") or url_for("dashboard")
            return redirect(next_page)
        flash("Contraseña incorrecta.", "error")
    return render_template("login.html", **_ruta("/login"))


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("tienda.catalogo"))


# ─── Helpers ──────────────────────────────────────────────────────

def _ruta(actual=""):
    """Retorna contexto con la ruta actual para el menú activo."""
    return {"ruta": actual}


def _formatear_pesos(valor):
    if valor is None or valor == 0:
        return "-"
    return f"$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _guardar_imagen_producto(producto_id, nombre_producto, proveedor_id, imagen):
    if not imagen or not getattr(imagen, "filename", ""):
        return None

    try:
        prv = db.get_proveedores()
        prv_nombre = next((p["nombre"] for p in prv if p["id"] == proveedor_id), "sin_proveedor")
        safe_prv = secure_filename(prv_nombre or "sin_proveedor") or "sin_proveedor"
        dest_dir = os.path.join(IMAGENES_DIR, "proveedores", safe_prv)
        os.makedirs(dest_dir, exist_ok=True)

        ext = os.path.splitext(imagen.filename)[1].lower() or ".jpg"
        safe_nombre = secure_filename(nombre_producto or f"producto_{producto_id}") or f"producto_{producto_id}"
        nombre_img = f"{producto_id}_{safe_nombre[:40]}{ext}"
        ruta_img = os.path.join(dest_dir, nombre_img)
        imagen.save(ruta_img)

        rel_path = os.path.relpath(ruta_img, BASE_DIR)
        db.add_imagen(producto_id, rel_path, es_principal=True)
        return rel_path
    except Exception as exc:
        flash(f"No se pudo guardar la imagen: {exc}", "error")
        return None


def _parsear_numero_form(valor, default=None):
    if valor is None:
        return default
    texto = str(valor).strip()
    if texto == "":
        return default
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        raise ValueError("Valor numérico inválido")


@app.context_processor
def inject_globals():
    return {"ruta": request.path}


# ─── Dashboard ────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("tienda.catalogo"))

@app.route("/dashboard")
@login_required
def dashboard():
    productos = db.get_productos()
    proveedores = db.get_proveedores()
    inversion_total = sum(p["costo"] * max(p["stock"], 1) for p in productos if p.get("costo"))
    venta_potencial = sum(
        (p["precio_venta"] or 0) * max(p["stock"], 1) for p in productos
    )
    ganancia_estimada = venta_potencial - inversion_total
    sin_precio = sum(1 for p in productos if not p.get("precio_venta"))
    ultimos = sorted(productos, key=lambda x: x.get("created_at") or "", reverse=True)[:6]

    # get images for ultimos
    for p in ultimos:
        imgs = db.get_imagenes(p["id"])
        p["imagen"] = imgs[0]["archivo"] if imgs else None

    stats = {
        "productos_activos": len(productos),
        "proveedores": len(proveedores),
        "inversion_total": inversion_total,
        "venta_potencial": venta_potencial,
        "ganancia_estimada": max(0, ganancia_estimada),
        "sin_precio": sin_precio,
        "ultimos_productos": ultimos,
    }
    return render_template("index.html", stats=stats, **_ruta("/dashboard"))


# ─── Productos ────────────────────────────────────────────────────

@app.route("/productos")
@login_required
def productos_listar():
    proveedor_id = request.args.get("proveedor", type=int)
    categoria = request.args.get("categoria")
    productos = db.get_productos(proveedor_id=proveedor_id, categoria=categoria)
    categorias = sorted(set(p.get("categoria") for p in productos if p.get("categoria")))
    return render_template("productos.html", productos=productos, categorias=categorias, **_ruta("/productos"))


@app.route("/productos/nuevo", methods=["GET", "POST"])
@login_required
def productos_nuevo():
    try:
        proveedores = db.get_proveedores()
        if not proveedores:
            flash("Primero creá un proveedor.", "error")
            return redirect(url_for("proveedores_nuevo"))

        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            if not nombre:
                flash("El nombre del producto es obligatorio.", "error")
                return redirect(url_for("productos_nuevo"))

            descripcion = request.form.get("descripcion", "").strip()
            proveedor_id = int(request.form.get("proveedor_id", 0) or 0)
            costo = _parsear_numero_form(request.form.get("costo"), default=0)
            costo_usd = _parsear_numero_form(request.form.get("costo_usd"), default=None)
            precio_venta = _parsear_numero_form(request.form.get("precio_venta"), default=None)
            categoria = request.form.get("categoria", "").strip()
            stock = int(request.form.get("stock", 0) or 0)
            iva = _parsear_numero_form(request.form.get("iva_porcentaje"), default=21)
            publicar = 1 if request.form.get("publicar") else 0

            pid = db.add_producto(
                nombre=nombre, descripcion=descripcion,
                proveedor_id=proveedor_id, costo=costo,
                categoria=categoria, stock=stock, iva_porcentaje=iva,
                publicar=publicar,
            )
            if costo_usd is not None:
                db.update_producto(pid, costo_usd=costo_usd)
                if not precio_venta:
                    calc = pcalc.calcular_precio_desde_usd(costo_usd, margen=35)
                    precio_venta = calc["precio_final"]
                    db.update_producto(pid, costo=calc["costo_ars"])
            elif costo and not precio_venta:
                precio_venta = pcalc.calcular_precio_venta_rapido(costo, margen=35)

            if precio_venta:
                db.update_producto(pid, precio_venta=precio_venta)

            imagen = request.files.get("imagen")
            _guardar_imagen_producto(pid, nombre, proveedor_id, imagen)

            flash(f"Producto '{nombre}' creado.", "success")
            return redirect(url_for("productos_detalle", id=pid))

        return render_template("producto_form.html", producto=None, proveedores=proveedores,
                               **_ruta("/productos"))
    except Exception as e:
        logging.error("Error en productos_nuevo: %s", traceback.format_exc())
        flash(f"Error inesperado: {e}", "error")
        return redirect(url_for("productos_listar"))


@app.route("/productos/<int:id>")
@login_required
def productos_detalle(id):
    try:
        p = db.get_producto(id)
        if not p:
            flash("Producto no encontrado.", "error")
            return redirect(url_for("productos_listar"))
        imgs = db.get_imagenes(id)
        p["imagenes"] = imgs
        p["imagen_principal"] = imgs[0]["archivo"] if imgs else None
        return render_template("producto_detail.html", p=p, **_ruta("/productos"))
    except Exception as e:
        logging.error("Error en productos_detalle(%s): %s", id, traceback.format_exc())
        flash(f"Error inesperado: {e}", "error")
        return redirect(url_for("productos_listar"))


@app.route("/productos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def productos_editar(id):
    try:
        p = db.get_producto(id)
        if not p:
            flash("Producto no encontrado.", "error")
            return redirect(url_for("productos_listar"))
        proveedores = db.get_proveedores()
        imgs = db.get_imagenes(id)
        p["imagenes"] = imgs

        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            if not nombre:
                flash("El nombre del producto es obligatorio.", "error")
                return redirect(url_for("productos_editar", id=id))

            costo_input = request.form.get("costo", "")
            costo = _parsear_numero_form(costo_input, default=p.get("costo", 0))
            costo_usd = _parsear_numero_form(request.form.get("costo_usd"), default=None)
            precio_venta = _parsear_numero_form(request.form.get("precio_venta"), default=None)
            proveedor_id = int(request.form.get("proveedor_id", 0) or 0)
            stock = int(request.form.get("stock", 0) or 0)
            iva = _parsear_numero_form(request.form.get("iva_porcentaje"), default=21)

            if costo_usd is not None and not precio_venta:
                calc = pcalc.calcular_precio_desde_usd(costo_usd, margen=35)
                precio_venta = calc["precio_final"]
                costo = calc["costo_ars"]
            elif costo is not None and not precio_venta:
                precio_venta = pcalc.calcular_precio_venta_rapido(costo, margen=35)

            db.update_producto(id,
                nombre=nombre,
                descripcion=request.form.get("descripcion", "").strip(),
                proveedor_id=proveedor_id,
                costo=costo,
                costo_usd=costo_usd,
                precio_venta=precio_venta,
                categoria=request.form.get("categoria", "").strip(),
                stock=stock,
                iva_porcentaje=iva,
                publicar=1 if request.form.get("publicar") else 0,
            )

            imagen = request.files.get("imagen")
            _guardar_imagen_producto(id, nombre, proveedor_id, imagen)

            flash("Producto actualizado.", "success")
            return redirect(url_for("productos_detalle", id=id))

        return render_template("producto_form.html", producto=p, proveedores=proveedores,
                               **_ruta("/productos"))
    except Exception as e:
        logging.error("Error en productos_editar(%s): %s", id, traceback.format_exc())
        flash(f"Error inesperado: {e}", "error")
        return redirect(url_for("productos_listar"))


@app.route("/productos/<int:id>/eliminar", methods=["POST"])
@login_required
def productos_eliminar(id):
    db.delete_producto(id)
    flash("Producto eliminado.", "success")
    return redirect(url_for("productos_listar"))


@app.route("/productos/<int:id>/toggle-publicar", methods=["POST"])
@login_required
def productos_toggle_publicar(id):
    p = db.get_producto(id)
    if p:
        nuevo = 0 if p.get("publicar") else 1
        db.update_producto(id, publicar=nuevo)
        flash(f"{'Publicado' if nuevo else 'Ocultado'} en tienda.", "success")
    return redirect(url_for("productos_detalle", id=id))


# ─── Imágenes (admin) ─────────────────────────────────────────────

@app.route("/imagenes/<int:id>/eliminar", methods=["POST"])
@login_required
def imagen_eliminar(id):
    conn = db.get_connection()
    img = conn.execute("SELECT * FROM imagenes WHERE id=?", (id,)).fetchone()
    if not img:
        flash("Imagen no encontrada.", "error")
        conn.close()
        return redirect(url_for("productos_listar"))
    pid = img["producto_id"]
    conn.execute("DELETE FROM imagenes WHERE id=?", (id,))
    conn.commit()
    conn.close()
    # Optionally delete the file
    fpath = img["archivo"]
    if os.path.exists(fpath) and os.path.isfile(fpath):
        os.remove(fpath)
    flash("Imagen eliminada.", "success")
    return redirect(url_for("productos_detalle", id=pid))


# ─── Proveedores ──────────────────────────────────────────────────

@app.route("/proveedores")
@login_required
def proveedores_listar():
    proveedores = db.get_proveedores()
    for prv in proveedores:
        prods = db.get_productos(proveedor_id=prv["id"])
        prv["cantidad_productos"] = len(prods)
    return render_template("proveedores.html", proveedores=proveedores, **_ruta("/proveedores"))


@app.route("/proveedores/nuevo", methods=["GET", "POST"])
@login_required
def proveedores_nuevo():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        contacto = request.form.get("contacto", "").strip()
        notas = request.form.get("notas", "").strip()
        pid = db.add_proveedor(nombre, contacto, notas)
        if pid:
            flash(f"Proveedor '{nombre}' creado.", "success")
            return redirect(url_for("proveedores_listar"))
        flash(f"El proveedor '{nombre}' ya existe.", "error")
    return render_template("proveedor_form.html", proveedor=None, **_ruta("/proveedores"))


@app.route("/proveedores/<int:id>/editar", methods=["GET", "POST"])
@login_required
def proveedores_editar(id):
    proveedores = db.get_proveedores()
    proveedor = next((p for p in proveedores if p["id"] == id), None)
    if not proveedor:
        flash("Proveedor no encontrado.", "error")
        return redirect(url_for("proveedores_listar"))
    if request.method == "POST":
        db.update_proveedor(id, nombre=request.form.get("nombre", ""),
                            contacto=request.form.get("contacto", ""),
                            notas=request.form.get("notas", ""))
        flash("Proveedor actualizado.", "success")
        return redirect(url_for("proveedores_listar"))
    return render_template("proveedor_form.html", proveedor=proveedor, **_ruta("/proveedores"))


# ─── Precios ──────────────────────────────────────────────────────

@app.route("/precios", methods=["GET", "POST"])
@login_required
def precios():
    datos = None
    resultado = None
    if request.method == "POST":
        try:
            costo = _parsear_numero_form(request.form.get("costo"), default=0)
            margen = _parsear_numero_form(request.form.get("margen_deseado"), default=35)
            datos = {"costo": costo, "margen_deseado": margen}
            params = pcalc.ParametrosPrecio(**datos)
            resultado = pcalc.calcular_precio_final(params)
        except ValueError:
            flash("Ingresá valores numéricos válidos para calcular el precio.", "error")
    return render_template("precios.html", datos=datos, resultado=resultado, **_ruta("/precios"))


@app.route("/precios/producto/<int:id>", methods=["GET", "POST"])
@login_required
def precios_producto(id):
    p = db.get_producto(id)
    if not p:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("productos_listar"))
    datos = {"margen_deseado": 35}
    resultado = None
    if request.method == "POST":
        try:
            datos["margen_deseado"] = _parsear_numero_form(request.form.get("margen_deseado"), default=35)
            params = pcalc.ParametrosPrecio(
                costo=p["costo"],
                margen_deseado=datos["margen_deseado"],
            )
            resultado = pcalc.calcular_precio_final(params)
        except ValueError:
            flash("Ingresá un margen válido para calcular el precio.", "error")
    return render_template("precios_producto.html", p=p, datos=datos, resultado=resultado,
                           **_ruta("/precios"))


@app.route("/precios/producto/<int:id>/guardar", methods=["POST"])
@login_required
def precios_producto_guardar(id):
    try:
        precio = _parsear_numero_form(request.form.get("precio_venta"), default=None)
        margen = _parsear_numero_form(request.form.get("margen_porcentaje"), default=None)
        if precio is None or margen is None:
            raise ValueError("faltan datos")
        db.update_producto(id, precio_venta=precio, margen_porcentaje=margen)
        flash("Precio guardado en el producto.", "success")
    except ValueError:
        flash("No se pudo guardar el precio porque faltan datos válidos.", "error")
    return redirect(url_for("productos_detalle", id=id))


# ─── Importar ─────────────────────────────────────────────────────

@app.route("/importar")
@login_required
def importar():
    return render_template("importar.html", candidatos=[], imagenes_copiadas=[],
                           proveedor="", **_ruta("/importar"))


@app.route("/importar/whatsapp")
@login_required
def importar_whatsapp_route():
    proveedor = request.args.get("proveedor", "")

    # Find the first txt in whatsapp_export
    txts = [f for f in os.listdir(importar_whatsapp.EXPORT_DIR)
            if f.endswith(".txt")] if os.path.isdir(importar_whatsapp.EXPORT_DIR) else []
    if not txts:
        flash("No hay archivos .txt en data/whatsapp_export/. Exportá un chat de WhatsApp con medios y ponelo ahí.", "error")
        return redirect(url_for("importar"))

    archivo = txts[0]
    try:
        resultado = importar_whatsapp.importar_desde_txt(proveedor or os.path.splitext(archivo)[0], archivo)
    except Exception as e:
        flash(f"Error al importar: {e}", "error")
        return redirect(url_for("importar"))

    candidatos = []
    for c in resultado["candidatos"]:
        candidatos.append({
            "remitente": c["remitente"],
            "descripcion": c["descripcion"],
            "nombre_sugerido": c["descripcion"][:40] if c["descripcion"] else "Producto",
            "archivo": "",
        })

    # Attach copied images to candidates
    if resultado["imagenes_copiadas"]:
        for i, img in enumerate(resultado["imagenes_copiadas"]):
            if i < len(candidatos):
                candidatos[i]["archivo"] = os.path.relpath(img["destino"], BASE_DIR)
                candidatos[i]["nombre_sugerido"] = os.path.splitext(os.path.basename(img["destino"]))[0][:40]

    return render_template("importar.html",
                           candidatos=candidatos,
                           imagenes_copiadas=resultado["imagenes_copiadas"],
                           proveedor=resultado["proveedor"],
                           **_ruta("/importar"))


@app.route("/importar/escanear")
@login_required
def importar_escanear_route():
    proveedor = request.args.get("proveedor", "")
    if not proveedor:
        # Show form to pick provider
        proveedores = db.get_proveedores()
        if proveedores:
            proveedor = proveedores[0]["nombre"]
        else:
            flash("No hay proveedores. Creá uno primero.", "error")
            return redirect(url_for("proveedores_nuevo"))

    try:
        productos = importar_whatsapp.escanear_carpeta_imagenes(proveedor)
    except Exception as e:
        flash(f"Error: {e}", "error")
        return redirect(url_for("importar"))

    candidatos = [{
        "archivo": p["archivo"],
        "nombre_sugerido": p["nombre_sugerido"],
        "descripcion": p["descripcion"],
        "remitente": proveedor,
    } for p in productos]

    return render_template("importar.html",
                           candidatos=candidatos,
                           imagenes_copiadas=[],
                           proveedor=proveedor,
                           **_ruta("/importar"))


@app.route("/importar/crear", methods=["POST"])
@login_required
def importar_crear():
    nombre = request.form.get("nombre", "").strip()[:60]
    descripcion = request.form.get("descripcion", "").strip()
    archivo = request.form.get("archivo", "")
    costo_str = request.form.get("costo", "0").strip()
    proveedor_nombre = request.form.get("proveedor", "").strip()

    try:
        costo = float(costo_str.replace(",", "."))
    except ValueError:
        costo = 0

    if not proveedor_nombre:
        flash("Especificá el proveedor.", "error")
        return redirect(url_for("importar_escanear_route"))

    # Get or create provider
    proveedores = db.get_proveedores()
    prv = next((p for p in proveedores if p["nombre"].lower() == proveedor_nombre.lower()), None)
    if not prv:
        pid = db.add_proveedor(proveedor_nombre)
        if not pid:
            flash(f"Error creando proveedor {proveedor_nombre}", "error")
            return redirect(url_for("importar"))
        prv = {"id": pid}

    # Create product
    product_id = db.add_producto(
        nombre=nombre or "Producto sin nombre",
        descripcion=descripcion,
        proveedor_id=prv["id"],
        costo=costo,
    )

    # Register image if exists
    if archivo and os.path.exists(os.path.join(BASE_DIR, archivo)):
        db.add_imagen(product_id, archivo, es_principal=True)

    flash(f"'{nombre}' creado desde importación.", "success")
    return redirect(url_for("productos_detalle", id=product_id))


# ─── Exportar ─────────────────────────────────────────────────────

@app.route("/exportar/<formato>")
@login_required
def exportar_ruta(formato):
    productos = db.get_productos()
    if not productos:
        flash("No hay productos para exportar.", "error")
        return redirect(url_for("dashboard"))

    try:
        if formato == "ml":
            ruta = exportar.exportar_mercadolibre_csv(productos)
            flash(f"CSV para Mercado Libre generado: {os.path.basename(ruta)}", "success")
        elif formato == "catalogo":
            ruta = exportar.exportar_catalogo_html(productos)
            flash(f"Catálogo web generado: {os.path.basename(ruta)}", "success")
        elif formato == "instagram":
            ruta = exportar.exportar_instagram_html(productos)
            flash(f"Posts para Instagram generados: {os.path.basename(ruta)}", "success")
        elif formato == "json":
            ruta = exportar.exportar_json(productos)
            flash(f"JSON exportado: {os.path.basename(ruta)}", "success")
        else:
            flash("Formato no soportado.", "error")
            return redirect(url_for("dashboard"))
    except Exception as e:
        flash(f"Error al exportar: {e}", "error")

    return redirect(url_for("dashboard"))


# ─── Imágenes (admin) ─────────────────────────────────────────────

IMAGENES_PROVEEDORES_DIR = os.path.join(IMAGENES_DIR, "proveedores")


def _imagenes_orfanas():
    """Return list of (archivo, proveedor_nombre, producto_id) for orphan images."""
    orfanas = []
    if not os.path.isdir(IMAGENES_PROVEEDORES_DIR):
        return orfanas
    for prv_dir in sorted(os.listdir(IMAGENES_PROVEEDORES_DIR)):
        prv_path = os.path.join(IMAGENES_PROVEEDORES_DIR, prv_dir)
        if not os.path.isdir(prv_path):
            continue
        for fname in sorted(os.listdir(prv_path)):
            if not fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            rel = os.path.join("imagenes", "proveedores", prv_dir, fname)
            # check if already linked
            conn = db.get_connection()
            row = conn.execute(
                "SELECT producto_id FROM imagenes WHERE archivo = ?", (rel,)
            ).fetchone()
            conn.close()
            if row is None:
                orfanas.append({"archivo": rel, "proveedor": prv_dir})
    return orfanas


@app.route("/imagenes")
@login_required
def imagenes_listar():
    orfanas = _imagenes_orfanas()
    productos = {p["id"]: p["nombre"] for p in db.get_productos(activos=False)}
    return render_template("imagenes.html", orfanas=orfanas, productos=productos,
                           **_ruta("/imagenes"))


@app.route("/imagenes/vincular/<path:archivo>", methods=["POST"])
@login_required
def imagenes_vincular(archivo):
    producto_id = request.form.get("producto_id")
    if not producto_id:
        flash("Seleccioná un producto.", "error")
        return redirect(url_for("imagenes_listar"))
    db.add_imagen(int(producto_id), archivo, es_principal=False)
    flash("Imagen vinculada.", "success")
    return redirect(url_for("imagenes_listar"))


# ─── Pedidos (admin) ─────────────────────────────────────────────

@app.route("/pedidos")
@login_required
def pedidos_listar():
    estado = request.args.get("estado")
    pedidos = db.get_pedidos(estado=estado)
    for ped in pedidos:
        items = db.get_pedido_items(ped["id"])
        ped["items"] = items
        ped["total_items"] = sum(i["cantidad"] for i in items)
    return render_template("pedidos.html", pedidos=pedidos, **_ruta("/pedidos"))


@app.route("/pedidos/<int:id>")
@login_required
def pedidos_detalle(id):
    pedido = db.get_pedido(id)
    if not pedido:
        flash("Pedido no encontrado.", "error")
        return redirect(url_for("pedidos_listar"))
    pedido["items"] = db.get_pedido_items(id)
    return render_template("pedido_detail.html", pedido=pedido, **_ruta("/pedidos"))


@app.route("/pedidos/<int:id>/estado", methods=["POST"])
@login_required
def pedidos_estado(id):
    estado = request.form.get("estado", "").strip()
    if estado in ("pendiente", "pagado", "enviado", "entregado", "cancelado"):
        db.actualizar_estado_pedido(id, estado)
        flash(f"Pedido #{id} actualizado a '{estado}'.", "success")
    else:
        flash("Estado inválido.", "error")
    return redirect(url_for("pedidos_detalle", id=id))


# ─── Servir imágenes ─────────────────────────────────────────────

@app.route("/imagenes/<path:filename>")
def servir_imagen(filename):
    return send_from_directory(IMAGENES_DIR, filename)


# ─── Configuración ─────────────────────────────────────────────────

@app.route("/configuracion", methods=["GET", "POST"])
@login_required
def configuracion():
    if request.method == "POST":
        config.set_many({
            "BANCO": request.form.get("BANCO", "").strip(),
            "BANCO_TITULAR": request.form.get("BANCO_TITULAR", "").strip(),
            "BANCO_CBU": request.form.get("BANCO_CBU", "").strip(),
            "BANCO_ALIAS": request.form.get("BANCO_ALIAS", "").strip(),
            "BANCO_TIPO": request.form.get("BANCO_TIPO", "Caja de Ahorro").strip(),
            "TIENDA_NOMBRE": request.form.get("TIENDA_NOMBRE", "Mi Tienda").strip(),
            "TIENDA_LOGO": request.form.get("TIENDA_LOGO", "").strip(),
            "TIENDA_COLOR": request.form.get("TIENDA_COLOR", "#2563eb").strip(),
            "TIENDA_DESCRIPCION": request.form.get("TIENDA_DESCRIPCION", "").strip(),
            "TIENDA_WA": request.form.get("TIENDA_WA", "#").strip(),
            "DOLAR_BLUE": request.form.get("DOLAR_BLUE", "1300").strip(),
            "DELIVERY_INFO": request.form.get("DELIVERY_INFO", "").strip(),
        })
        flash("Configuración guardada. Reinciá el servidor para aplicar cambios.", "success")
        return redirect(url_for("configuracion"))
    cfg = config.get_all()
    return render_template("configuracion.html", cfg=cfg, **_ruta("/configuracion"))


# ─── Error handlers ───────────────────────────────────────────────

@app.errorhandler(500)
def handle_500(e):
    logging.error("Error 500: %s", traceback.format_exc())
    return render_template("error.html", codigo=500, mensaje="Error interno del servidor"), 500

@app.errorhandler(404)
def handle_404(e):
    return render_template("error.html", codigo=404, mensaje="Página no encontrada"), 404


# ─── Init ──────────────────────────────────────────────────────
db.init_db()

admin_pass = config.get("ADMIN_PASSWORD")
if not admin_pass:
    print("⚠  ADMIN_PASSWORD no configurada. Usá la variable de entorno ADMIN_PASSWORD o configurá en data/config.json")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=port)
