"""
sistema-reventa — CLI para gestionar productos de reventa.

Uso:
    python app.py proveedores listar
    python app.py productos listar
    python app.py productos agregar
    python app.py precios calcular --costo 1000 --margen 35
    python app.py importar whatsapp --proveedor "Proveedor X"
    python app.py exportar ml
    python app.py exportar catalogo
    python app.py exportar instagram
"""

import argparse
import os
import re
import sys
import unicodedata
from datetime import datetime

import db
import precios as pcalc
import importar_whatsapp
import exportar


def cmd_init(args):
    db.init_db()
    print("Base de datos inicializada.")


# ─── Proveedores ──────────────────────────────────────────────────

def cmd_proveedores_listar(args):
    proveedores = db.get_proveedores()
    if not proveedores:
        print("No hay proveedores. Usá: python app.py proveedores agregar")
        return
    print(f"\n{'ID':<4} {'Nombre':<25} {'Contacto':<20} {'Notas'}")
    print("-" * 70)
    for p in proveedores:
        print(f"{p['id']:<4} {p['nombre']:<25} {(p['contacto'] or ''):<20} {p.get('notas', '')}")


def cmd_proveedores_agregar(args):
    pid = db.add_proveedor(args.nombre, args.contacto or "", args.notas or "")
    if pid:
        print(f"Proveedor '{args.nombre}' creado (ID {pid}).")
    else:
        print(f"El proveedor '{args.nombre}' ya existe.")


# ─── Productos ────────────────────────────────────────────────────

def cmd_productos_listar(args):
    productos = db.get_productos(
        activos=not args.inactivos,
        proveedor_id=args.proveedor,
        categoria=args.categoria,
    )
    if not productos:
        print("No hay productos.")
        return
    print(f"\n{'ID':<4} {'Nombre':<35} {'Costo':>10} {'Venta':>10} {'Stock':<6} {'Proveedor':<20}")
    print("-" * 90)
    for p in productos:
        costo = f"${p['costo']:,.0f}".replace(",", ".") if p['costo'] else "-"
        venta = f"${p['precio_venta']:,.0f}".replace(",", ".") if p['precio_venta'] else "-"
        print(f"{p['id']:<4} {p['nombre'][:34]:<35} {costo:>10} {venta:>10} {p['stock']:<6} {(p.get('proveedor_nombre') or ''):<20}")


def cmd_productos_agregar(args):
    proveedores = db.get_proveedores()
    if not proveedores:
        print("Primero creá un proveedor: python app.py proveedores agregar")
        return

    if not args.nombre:
        args.nombre = input("Nombre del producto: ").strip()
    if not args.descripcion:
        args.descripcion = input("Descripción: ").strip()
    if not args.costo:
        costo_str = input("Costo (solo número): ").strip()
        args.costo = float(costo_str.replace(",", "."))
    if not args.proveedor:
        print("\nProveedores disponibles:")
        for p in proveedores:
            print(f"  {p['id']}: {p['nombre']}")
        pid_str = input("ID del proveedor: ").strip()
        args.proveedor = int(pid_str)

    pid = db.add_producto(
        nombre=args.nombre,
        descripcion=args.descripcion or "",
        proveedor_id=args.proveedor,
        costo=args.costo,
        categoria=args.categoria or "",
        stock=args.stock or 0,
        iva_porcentaje=args.iva or 21,
    )
    print(f"Producto '{args.nombre}' creado (ID {pid}).")


def cmd_productos_editar(args):
    p = db.get_producto(args.id)
    if not p:
        print(f"Producto ID {args.id} no existe.")
        return
    print(f"Editando: {p['nombre']} (dejar vacío para mantener valor actual)")
    campos = [
        ("nombre", "Nombre", p["nombre"]),
        ("descripcion", "Descripción", p.get("descripcion", "")),
        ("costo", "Costo", str(p["costo"])),
        ("precio_venta", "Precio de venta", str(p.get("precio_venta") or "")),
        ("categoria", "Categoría", p.get("categoria", "")),
        ("stock", "Stock", str(p.get("stock", 0))),
    ]
    updates = {}
    for key, label, current in campos:
        val = input(f"  {label} [{current}]: ").strip()
        if val:
            if key in ("costo", "precio_venta", "stock"):
                try:
                    val = float(val.replace(",", "."))
                except ValueError:
                    print(f"  Valor inválido, se ignora.")
                    continue
            updates[key] = val
    if updates:
        db.update_producto(args.id, **updates)
        print("Producto actualizado.")
    else:
        print("Sin cambios.")


def cmd_productos_eliminar(args):
    p = db.get_producto(args.id)
    if not p:
        print(f"Producto ID {args.id} no existe.")
        return
    confirm = input(f"¿Eliminar '{p['nombre']}' (ID {args.id})? (s/N): ").strip().lower()
    if confirm == "s":
        db.delete_producto(args.id)
        print("Eliminado.")


def _quitar_acentos(t):
    return unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode('ascii')


def _normalizar_modelo(nombre):
    """Extrae el modelo/base del nombre del producto para detectar duplicados."""
    n = _quitar_acentos(nombre).lower().strip()

    # Remove parentheticals, special chars, collapse whitespace
    n = re.sub(r'\(.*?\)', ' ', n)
    n = re.sub(r'[^\w\s/-]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()

    # Strip known marketing prefixes (repeat to catch all layers)
    for _ in range(3):
        for p in [
            r'^(últimas?\s+)?unidades?\s+(no\s+)?reingresan?\s+',
            r'^última?\s+unidad\b', r'^promo\s+\w+\s+',
            r'^reingres[oa]\s+', r'^super\s+(reba|liquidacion)\s+',
            r'^(gran\s+)?liquidacion\s+', r'^preventa\s+',
            r'^(mega\s+)?combo\s+\w+\s+\w+\s+',
            r'^aprovech[ae]\s+', r'^solo\s+',
            r'^nuevos?\s+ingresos?\s+', r'^nuevo\s+',
            r'^no\s+reingresan\b', r'^ideal\s+(para\s+)?',
            r'^(\*\s*)?(ultimos?|ultimas?)\s+',
            r'^equipa\s+', r'^arma\s+', r'^renova\s+',
            r'^disponibles?\s+', r'^sale\s+',
            r'^pocas?\s+unidades\s+', r'^del?\s+',
        r'^(super\s+)?(re|pro)?mocion\s+',
        r'^(super\s+)?(re|pre)?cio\s+',
        r'^precio\s+especial\s+',
        r'^rebaja\s+(de\s+)?precios?\s+',
            r'^porque\s+', r'^emprendedor\s+',
            r'^et\s+', r'^dummy\s+',
        ]:
            n = re.sub(p, '', n).strip()

    # Strip trailing structured price/marketing info
    n = re.sub(r'(precios?\s+(especiales?\s+)?(mayoristas?)?|por\s+unidad|no\s+reingresan|de\s+ultimas?\s+unidades|rebaja\s+de\s+precios|oportunidad\s+unica\s+(para\s+)?(stockearte)?|precio\s+especial|precio\s+por\s+(unidad|cantidad)|precio\s+por\s+tiempo\s+limitado|por\s+tiempo\s+limitado|calidad\s+y\s+precio|vivi\s+una\s+experiencia|facilidades\s+de\s+pago|retiro\s+por|consultanos|escribinos)\s+[\w\s]*(usd\s*[\d\s.,/$%]+)?$', ' ', n)
    n = re.sub(r'\$[\d\s.,]+', ' ', n)
    n = re.sub(r'[\d]{2,3}([.,]\d+)?\s*(usd|dolares?)', ' ', n)
    n = re.sub(r'(usd|dolares?)\s*[\d\s.,]+', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()

    # If there's a known brand, extract from brand onwards up to a clean break
    brands = r'\b(samsung|xiaomi|redmi|poco|jbl|lg|tcl|bgh|gadnic|nuvoh|n[oó]made|siera|enova|hynurik|noga|pioneer|winco|daihatsu|lamborghini|hyundai|hisense|philco|noblex|atvio|ken\s*brown|cecotec|midea|whirlpool|geek\s*bar|supreme|ovns|kalley|vapear|sprint|hal[oó]gena)\b'
    brand_match = re.search(brands, n)
    if brand_match:
        start = brand_match.start()
        clave = n[start:start+80].strip()
    else:
        clave = n[:60].strip()
    clave = re.sub(r'\s+', ' ', clave).strip()
    if not brand_match and len(clave) < 10:
        clave = nombre.lower()[:50]
    return clave


def _limpiar_nombre(nombre):
    """Limpia el nombre del producto para mostrar en catalogo, sin texto marketing."""
    n = _quitar_acentos(nombre).strip()
    n = re.sub(r'\(.*?\)', ' ', n)
    n = re.sub(r'[^\w\s/\-áéíóúñÁÉÍÓÚÑ]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()

    prefijos = [
        r'^ultimas?\s+unidades?\s+',
        r'^ultima?\s+unidad\s+',
        r'^ultimas?\s+unidad\s+',
        r'^ultimos?\s+dias?\s+',
        r'^no\s+reingresan\s+',
        r'^promo\s+\w+\s+(del?\s+)?\w*\s*',
        r'^reingres[oa]\s+',
        r'^super\s+(reba|liquidacion|promocion|oferta|precio)\s+',
        r'^(gran\s+)?liquidacion\s+',
        r'^preventa\s+',
        r'^aprovech[ae]\s+',
        r'^solo\s+',
        r'^nuevos?\s+ingresos?\s+',
        r'^nuevo\s+',
        r'^ideal\s+(para\s+)?',
        r'^equipa\s+',
        r'^arma\s+',
        r'^renova\s+',
        r'^disponibles?\s+',
        r'^sale\s+',
        r'^pocas?\s+unidades\s+',
        r'^d[ei]l?\s+',
        r'^rebaja\s+(de\s+)?precios?\s+',
        r'^por\s+',
        r'^solo\s+por\s+',
        r'^porque\s+',
        r'^emprendedor\s+',
        r'^et\s+',
        r'^dummy\s+',
        r'^hot\s+sale\s+',
        r'^mundial\s+',
        r'^unica\s+unidad\s+',
        r'^en\s+stock\s+',
    ]
    for _ in range(3):
        for p in prefijos:
            n = re.sub(p, '', n, flags=re.IGNORECASE).strip()

    n = re.sub(
        r'(precios?\s+(especiales?\s+)?(mayoristas?)?'
        r'|por\s+unidad|no\s+reingresan|de\s+ultimas?\s+unidades'
        r'|rebaja\s+de\s+precios|por\s+tiempo\s+limitado'
        r'|calidad\s+y\s+precio|vivi\s+una\s+experiencia'
        r'|facilidades\s+de\s+pago|retiro\s+por|consultanos|escribinos'
        r'|oportunidad\s+unica\s+(para\s+)?(stockearte)?'
        r'|precio\s+especial|precio\s+por\s+(unidad|cantidad)'
        r'|promo\s+(semanal|especial)|te\s+lo\s+llevas'
        r'|pocas?\s+unidades\s+\d+\s+unidad'
        r'|ultimas?\s+disponibles?'
        r'|precios\s+mayoristas?\s+\d+\s+unidad'
        r'|el\s+regalo\s+perfecto'
        r'|la\s+mejor\s+opcion'
        r'|nunca\s+fall'
        r'|en\s+stock\s+hasta\s+nuevo\s+aviso'
        r'|hace\s+tu\s+pedido'
        r'|disfruta\s+cafe'
        r'|solo\s+\d+\s+unidades'
        r'|pro\s+bass'
        r'|precios\s+mayorist'
        r'|calidad\s+premium'
        r'|excelente\s+salida'
        r'|stockeate|stockear'
        r'|aprovecha|aproveche'
        r'|renova\s+tu'
        r'|convierta|converti'
        r'|ideal\s+(para\s+)?(eventos|locales|disfrutar|uso|dejar)'
        r'|disfruta\s+tus'
        r'|todo\s+lo\s+que\s+necesitas'
        r'|la\s+mejor\s+experiencia'
        r'|unica\s+unidad\s+disponible'
        r'|copa\s+del\s+mundo'
        r'|regalar\s+este\s+domingo)'
        r'\s+.*$', '', n, flags=re.IGNORECASE
    )

    # Strip trailing remaining fluff  
    for pat in [
        r'\b(precios?\s+(especiales?\s+)?(mayoristas?)?|precio\s+especial|consultanos|escribinos|envio\s+gratis|ultimas\s+unidades|disponibles?|no\s+reingresan)\s*$',
        r'[\d\s.$%/+\-*|:;]+\s*$',
    ]:
        n = re.sub(pat, ' ', n, flags=re.IGNORECASE).strip()
    n = re.sub(r'\$[\d\s.,]+(\s*usd)?', ' ', n, flags=re.IGNORECASE)
    n = re.sub(r'[\d]{2,3}([.,]\d+)?\s*(usd|dolares?)', ' ', n, flags=re.IGNORECASE)
    n = re.sub(r'(usd|dolares?)\s*[\d\s.,]+', ' ', n, flags=re.IGNORECASE)
    n = re.sub(r'\s+', ' ', n).strip().rstrip(',').strip()

    # Capitalize properly
    palabras = n.split()
    result = []
    for w in palabras:
        if w.lower() in ('de', 'del', 'la', 'el', 'los', 'las', 'con', 'sin', 'y', 'e', 'o', 'a', 'en', 'un', 'una', 'por', 'para', 'al', 'su'):
            result.append(w.lower())
        elif w.lower() in ('tv', 'hd', 'full', 'gb', 'ram', 'usb', 'mtb', 'mp', 'wi-fi', 'wifi'):
            result.append(w.upper())
        elif w.lower().startswith('4k'):
            result.append('4K')
        else:
            result.append(w[0].upper() + w[1:] if len(w) > 1 else w.upper())
    n = ' '.join(result)

    return n[:80] if n else nombre[:80].strip()


def cmd_productos_limpiar(args):
    """Limpia catálogo: desactiva tests, elimina combos/promos, limpia nombres."""
    test_ids = {1, 2, 3, 4}
    for tid in test_ids:
        p = db.get_producto(tid)
        if p and p.get("activo"):
            db.update_producto(tid, activo=0)
            print(f"  ⊘ Test desactivado: ID {tid} - {p['nombre'][:40]}")

    # Delete combo/promo/mega products
    todos = db.get_productos(activos=False)
    eliminados = 0
    delete_pattern = re.compile(r'^(COMBO|PROMO|MEGA)\b', re.IGNORECASE)
    for p in todos:
        if delete_pattern.match(p["nombre"]):
            db.delete_producto(p["id"])
            eliminados += 1

    print(f"  ✗ {eliminados} productos combo/promo eliminados.")

    # Clean names of remaining active products
    restantes = db.get_productos(activos=True)
    limpiados = 0
    for p in restantes:
        limpio = _limpiar_nombre(p["nombre"])
        if limpio and limpio != p["nombre"]:
            db.update_producto(p["id"], nombre=limpio)
            limpiados += 1

    print(f"  ✓ {limpiados} nombres limpiados.")
    print(f"  → Quedan {len(restantes) - eliminados} productos activos en catálogo.")


def cmd_productos_deduplicar(args):
    """Detecta y fusiona productos duplicados por modelo."""
    productos = db.get_productos(activos=False)
    grupos = {}
    for p in productos:
        clave = _normalizar_modelo(p["nombre"])
        if clave not in grupos:
            grupos[clave] = []
        grupos[clave].append(p)

    total_dup = sum(len(v) - 1 for v in grupos.values() if len(v) > 1)
    if total_dup == 0:
        print("No se encontraron duplicados.")
        return

    print(f"🔍 Detectados {total_dup} productos duplicados en {sum(1 for v in grupos.values() if len(v) > 1)} grupos.\n")

    if args.dry_run:
        print(f"{'Clave':<45} {'Cant':<5} {'IDs'}")
        print("-" * 70)
        for clave, prods in sorted(grupos.items()):
            if len(prods) > 1:
                ids = ", ".join(str(p["id"]) for p in prods)
                print(f"{clave[:44]:<45} {len(prods):<5} {ids}")
        print(f"\n💡 Ejecutá sin --dry-run para fusionar.")
        return

    fusionados = 0
    for clave, prods in grupos.items():
        if len(prods) <= 1:
            continue

        # Keep the product with the shortest name (cleanest)
        prods.sort(key=lambda p: len(p["nombre"]))
        keeper = prods[0]
        dups = prods[1:]

        # Merge images from duplicates to keeper
        for d in dups:
            imgs = db.get_imagenes(d["id"])
            for img in imgs:
                db.add_imagen(keeper["id"], img["archivo"], es_principal=img["es_principal"])

            # Delete duplicate product
            db.delete_producto(d["id"])

        fusionados += len(dups)

        if not args.quiet:
            print(f"  ✓ {keeper['nombre'][:40]:<42} → {keeper['id']} (fusionados {len(dups)} dups)")

    print(f"\n✅ {fusionados} productos duplicados fusionados.")


def cmd_productos_info(args):
    p = db.get_producto(args.id)
    if not p:
        print(f"Producto ID {args.id} no existe.")
        return
    imagenes = db.get_imagenes(args.id)
    print(f"\nID: {p['id']}")
    print(f"Nombre: {p['nombre']}")
    print(f"Descripción: {p.get('descripcion', '')}")
    print(f"Proveedor: {p.get('proveedor_nombre', '')}")
    print(f"Costo: ${p['costo']:,.2f}")
    print(f"Precio venta: ${p.get('precio_venta', 0):,.2f}" if p.get('precio_venta') else "Precio venta: sin definir")
    print(f"Categoría: {p.get('categoria', '')}")
    print(f"Stock: {p.get('stock', 0)}")
    print(f"Imágenes: {len(imagenes)}")
    for img in imagenes:
        print(f"  {'★' if img['es_principal'] else '○'} {img['archivo']}")


# ─── Precios ──────────────────────────────────────────────────────

def cmd_precios_calcular(args):
    params = pcalc.ParametrosPrecio(
        costo=args.costo,
        margen_deseado=args.margen,
    )
    resultado = pcalc.calcular_precio_final(params)
    print(f"\n{'='*35}")
    print(f"  Cálculo de precio")
    print(f"{'='*35}")
    print(f"  Costo:           $ {resultado['costo']:>8,.2f}")
    print(f"  Margen:          {params.margen_deseado:.0f}%")
    print(f"  {'─'*20}")
    print(f"  PRECIO FINAL     $ {resultado['precio_final']:>8,.2f}")
    print(f"  {'─'*20}")
    print(f"  Ganancia:        $ {resultado['ganancia']:>8,.2f}")
    print(f"  Margen s/costo:  {resultado['margen_porcentaje']:>7.1f}%")
    print()


def cmd_precios_producto(args):
    p = db.get_producto(args.id)
    if not p:
        print(f"Producto ID {args.id} no existe.")
        return
    params = pcalc.ParametrosPrecio(
        costo=p["costo"],
        margen_deseado=args.margen or 35,
    )
    resultado = pcalc.calcular_precio_final(params)
    print(f"\n  Producto: {p['nombre']}")
    print(f"  Costo actual: $ {p['costo']:,.2f}")
    print(f"  Precio sugerido: $ {resultado['precio_final']:,.2f}")
    if args.guardar:
        db.update_producto(args.id, precio_venta=resultado["precio_final"],
                           margen_porcentaje=resultado["margen_porcentaje"])
        print("  ✓ Precio guardado en el producto.")


# ─── Importar ─────────────────────────────────────────────────────

def cmd_importar_whatsapp(args):
    try:
        resultado = importar_whatsapp.importar_desde_txt(args.proveedor, args.archivo)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    if args.auto:
        print(f"\n⏳ Creando productos automáticamente...\n")
        res = importar_whatsapp.auto_crear_productos(resultado, margen=args.margen)
        print(f"✅ Creados: {len(res['creados'])}")
        print(f"⏭️  Saltados: {len(res['saltados'])}")
        print(f"❌ Errores: {len(res['errores'])}")
        if res["creados"]:
            print(f"\n{'ID':<4} {'Nombre':<35} {'Costo':>10} {'Venta':>10} {'Img':<4}")
            print("-" * 65)
            for c in res["creados"]:
                img = "✓" if c["imagen"] else "✗"
                print(f"{c['id']:<4} {c['nombre'][:34]:<35} ${c['costo']:>7,.0f} ${c['precio_venta']:>7,.0f} {img:<4}")
        if res["saltados"]:
            print(f"\n⏭️  Saltados ({len(res['saltados'])}):")
            for s in res["saltados"]:
                nom = s["candidato"].get("nombre_sugerido", "?")
                print(f"  · {nom} — {s['motivo']}")
        if res["errores"]:
            print(f"\n❌ Errores ({len(res['errores'])}):")
            for e in res["errores"]:
                print(f"  · {e['motivo']}")
        return

    print(f"\nProveedor: {resultado['proveedor']}")
    print(f"Archivo: {resultado['archivo']}")
    print(f"\nCandidatos a producto encontrados: {len(resultado['candidatos'])}")
    for c in resultado["candidatos"]:
        desc = c["descripcion"][:80] if c["descripcion"] else "(sin descripción)"
        precio = f" — ${c['precio']:,.0f}" if c.get("precio") else ""
        print(f"  · {c['remitente']}: {desc}{precio}")

    if resultado["imagenes_copiadas"]:
        print(f"\nImágenes copiadas: {len(resultado['imagenes_copiadas'])}")
        dest = os.path.dirname(resultado["imagenes_copiadas"][0]["destino"])
        print(f"  → {dest}")

    print(f"\n💡 Usá --auto para crear los productos automáticamente:")
    print(f"   python app.py importar whatsapp --proveedor \"{args.proveedor}\" --auto")


def cmd_importar_escanear(args):
    productos = importar_whatsapp.escanear_carpeta_imagenes(args.proveedor)
    if not productos:
        print(f"No se encontraron imágenes en imagenes/proveedores/{args.proveedor}/")
        return
    print(f"\nImágenes encontradas: {len(productos)}")
    for p in productos:
        print(f"  · {p['nombre_sugerido']}")
    print(f"\n💡 Agregalos con: python app.py productos agregar")


# ─── Exportar ─────────────────────────────────────────────────────

def cmd_exportar(args):
    filtros = {}
    if args.proveedor:
        filtros["proveedor_id"] = args.proveedor
    if args.categoria:
        filtros["categoria"] = args.categoria
    productos = db.get_productos(**filtros)

    if not productos:
        print("No hay productos para exportar.")
        return

    if args.formato == "ml":
        ruta = exportar.exportar_mercadolibre_csv(productos, args.output)
    elif args.formato == "catalogo":
        ruta = exportar.exportar_catalogo_html(productos, args.output)
    elif args.formato == "instagram":
        ruta = exportar.exportar_instagram_html(productos, args.output)
    elif args.formato == "json":
        ruta = exportar.exportar_json(productos, args.output)
    else:
        print(f"Formato '{args.formato}' no soportado.")
        return
    print(f"Exportado: {ruta}")


# ─── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sistema de gestión para reventa",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python app.py init
  python app.py proveedores agregar "Distribuidora X"
  python app.py productos agregar --proveedor 1
  python app.py precios calcular --costo 1500 --margen 35
  python app.py precios producto 1 --guardar
  python app.py importar whatsapp --proveedor "Distribuidora X"
  python app.py exportar ml
  python app.py exportar instagram
        """,
    )
    parser.add_argument("--db", help="Ruta de la base de datos")
    sub = parser.add_subparsers(dest="comando")
    sub.required = True

    # init
    p = sub.add_parser("init", help="Inicializar base de datos")
    p.set_defaults(func=cmd_init)

    # proveedores
    p = sub.add_parser("proveedores", help="Gestionar proveedores")
    p_sub = p.add_subparsers(dest="subcomando")
    p_sub.required = True

    p2 = p_sub.add_parser("listar", help="Listar proveedores")
    p2.set_defaults(func=cmd_proveedores_listar)

    p2 = p_sub.add_parser("agregar", help="Agregar proveedor")
    p2.add_argument("nombre", help="Nombre del proveedor")
    p2.add_argument("--contacto", help="Teléfono / email")
    p2.add_argument("--notas", help="Notas adicionales")
    p2.set_defaults(func=cmd_proveedores_agregar)

    # productos
    p = sub.add_parser("productos", help="Gestionar productos")
    p_sub = p.add_subparsers(dest="subcomando")
    p_sub.required = True

    p2 = p_sub.add_parser("listar", help="Listar productos")
    p2.add_argument("--inactivos", action="store_true", help="Incluir inactivos")
    p2.add_argument("--proveedor", type=int, help="Filtrar por ID de proveedor")
    p2.add_argument("--categoria", help="Filtrar por categoría")
    p2.set_defaults(func=cmd_productos_listar)

    p2 = p_sub.add_parser("agregar", help="Agregar producto (interactivo)")
    p2.add_argument("--nombre", help="Nombre del producto")
    p2.add_argument("--descripcion", help="Descripción")
    p2.add_argument("--costo", type=float, help="Costo")
    p2.add_argument("--proveedor", type=int, help="ID del proveedor")
    p2.add_argument("--categoria", help="Categoría")
    p2.add_argument("--stock", type=int, default=0, help="Stock inicial")
    p2.add_argument("--iva", type=float, default=21, help="IVA %% (default: 21)")
    p2.set_defaults(func=cmd_productos_agregar)

    p2 = p_sub.add_parser("editar", help="Editar producto (interactivo)")
    p2.add_argument("id", type=int, help="ID del producto")
    p2.set_defaults(func=cmd_productos_editar)

    p2 = p_sub.add_parser("eliminar", help="Eliminar producto")
    p2.add_argument("id", type=int, help="ID del producto")
    p2.set_defaults(func=cmd_productos_eliminar)

    p2 = p_sub.add_parser("limpiar", help="Limpiar catálogo: test, combos, nombres")
    p2.set_defaults(func=cmd_productos_limpiar)

    p2 = p_sub.add_parser("deduplicar", help="Fusionar productos duplicados por nombre")
    p2.add_argument("--dry-run", action="store_true", help="Solo listar duplicados sin fusionar")
    p2.add_argument("--quiet", action="store_true", help="No mostrar cada fusión")
    p2.set_defaults(func=cmd_productos_deduplicar)

    p2 = p_sub.add_parser("info", help="Ver detalle de producto")
    p2.add_argument("id", type=int, help="ID del producto")
    p2.set_defaults(func=cmd_productos_info)

    # precios
    p = sub.add_parser("precios", help="Calcular precios")
    p_sub = p.add_subparsers(dest="subcomando")

    p2 = p_sub.add_parser("calcular", help="Calcular precio desde costo")
    p2.add_argument("--costo", type=float, required=True, help="Costo del producto")
    p2.add_argument("--margen", type=float, default=35, help="Margen de ganancia %% (default: 35)")
    p2.set_defaults(func=cmd_precios_calcular)

    p2 = p_sub.add_parser("producto", help="Calcular precio sugerido para un producto existente")
    p2.add_argument("id", type=int, help="ID del producto")
    p2.add_argument("--margen", type=float, default=35, help="Margen de ganancia %% (default: 35)")
    p2.add_argument("--guardar", action="store_true", help="Guardar el precio calculado")
    p2.set_defaults(func=cmd_precios_producto)

    # importar
    p = sub.add_parser("importar", help="Importar productos")
    p_sub = p.add_subparsers(dest="subcomando")
    p_sub.required = True

    p2 = p_sub.add_parser("whatsapp", help="Importar desde exportación de WhatsApp")
    p2.add_argument("--proveedor", required=True, help="Nombre del proveedor")
    p2.add_argument("--archivo", help="Nombre del .txt en data/whatsapp_export/")
    p2.add_argument("--auto", action="store_true", help="Crear productos automáticamente")
    p2.add_argument("--margen", type=float, default=35, help="Margen de ganancia %% (default: 35)")
    p2.set_defaults(func=cmd_importar_whatsapp)

    p2 = p_sub.add_parser("escanear", help="Escanea carpeta de imágenes de un proveedor")
    p2.add_argument("--proveedor", required=True, help="Nombre del proveedor (carpeta en imagenes/proveedores/)")
    p2.set_defaults(func=cmd_importar_escanear)

    # exportar
    p = sub.add_parser("exportar", help="Exportar productos")
    p.add_argument("formato", choices=["ml", "catalogo", "instagram", "json"],
                   help="Formato de exportación")
    p.add_argument("--output", help="Nombre del archivo de salida")
    p.add_argument("--proveedor", type=int, help="Filtrar por proveedor")
    p.add_argument("--categoria", help="Filtrar por categoría")
    p.set_defaults(func=cmd_exportar)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
