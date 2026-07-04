"""
Importa productos desde exportación de WhatsApp.

Uso:
    1. En WhatsApp: exportar chat (con medios) a archivo .txt
    2. Copiar el .txt y la carpeta de imágenes a data/whatsapp_export/
    3. Ejecutar: python app.py importar whatsapp
    4. Opcional: python app.py importar whatsapp --proveedor "X" --auto
"""

import os
import re
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
EXPORT_DIR = os.path.join(BASE_DIR, "data", "whatsapp_export")
IMAGENES_DIR = os.path.join(BASE_DIR, "imagenes", "proveedores")


def _listar_archivos_txt():
    if not os.path.isdir(EXPORT_DIR):
        return []
    return [f for f in os.listdir(EXPORT_DIR) if f.endswith(".txt")]


def _normalizar_nombre_archivo(origen, proveedor, index):
    ext = os.path.splitext(origen)[1].lower()
    fecha = datetime.now().strftime("%Y%m%d")
    nombre = f"{proveedor}_{index:03d}_{fecha}{ext}"
    return nombre


def _parsear_whatsapp_texto(ruta_txt):
    """
    Parsea archivo de exportación de WhatsApp.
    Formatos soportados:
        [14/1/2024 10:30:45] Juan: texto         (Android viejo)
        13/6/2026, 15:14 - Juan: texto            (Android nuevo / iPhone)
    Retorna lista de dicts con: timestamp, remitente, texto
    """
    patron_moderno = re.compile(
        r"\u200e?(\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}(?::\d{2})?(?: [ap]\. m\.)?)\s*-\s*([^:]+):\s*(.*)"
    )
    patron_antiguo = re.compile(
        r"\u200e?\[(\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}(?::\d{2})?(?: [ap]\. m\.)?)\]\s*([^:]+):\s*(.*)"
    )
    mensajes = []
    with open(ruta_txt, encoding="utf-8", errors="replace") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            m = patron_moderno.match(linea) or patron_antiguo.match(linea)
            if m:
                timestamp_str = m.group(1).strip()
                remitente = m.group(2).strip()
                texto = m.group(3).strip()
                mensajes.append({
                    "timestamp": timestamp_str,
                    "remitente": remitente,
                    "texto": texto,
                })
            elif mensajes:
                mensajes[-1]["texto"] += " " + linea
    return mensajes


def _extraer_nombre_archivo_imagen(texto):
    """Extrae el nombre del archivo IMG de un mensaje de WhatsApp, ej: IMG-20260613-WA0001.jpg"""
    m = re.search(r"(IMG-\S+\.\w+)", texto, re.IGNORECASE)
    return m.group(1) if m else None


def _extraer_precio(texto):
    """
    Extrae el primer precio en ARS de un texto.

    Formatos soportados:
        $213.150, $ 213.150, $1.234.567, $1500, USD | $213.150
    Retorna float o None.
    """
    texto_limpio = texto.replace("*", "").replace("_", "").strip()
    texto_limpio = re.sub(r"[\u200e\u200f]", "", texto_limpio)

    # Buscar $ seguido de número (puede tener puntos como separador de miles)
    m = re.search(r'\$\s*([\d]{1,3}(?:\.[\d]{3})*(?:[\.,]\d+)?)', texto_limpio)
    if m:
        val = m.group(1)
        val = val.replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass

    # Buscar también "USD" con barra o pipe seguido de $
    m = re.search(r'USD\s*[|/]\s*\$\s*([\d]{1,3}(?:\.[\d]{3})*(?:[\.,]\d+)?)', texto_limpio)
    if m:
        val = m.group(1)
        val = val.replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass

    # Buscar número directamente con formato argentino
    m = re.search(r'(?<!\w)([\d]{2,3}(?:\.[\d]{3})+(?:[\.,]\d+)?)\s*$', texto_limpio)
    if m:
        val = m.group(1)
        val = val.replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass

    return None


def _extraer_precio_usd(texto):
    """Extrae precio en USD de un texto. Busca formatos como USD 20, U$D 20, usd 20."""
    texto_limpio = texto.replace("*", "").replace("_", "").strip()
    texto_limpio = re.sub(r"[\u200e\u200f]", "", texto_limpio)

    # USD 20, U$D 20, usd 20, USD20
    m = re.search(r'(?:USD|U\$S?|usd)\s*:?\s*([\d]{1,3}(?:[.,][\d]{3})*(?:[.,]\d+)?)', texto_limpio, re.IGNORECASE)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass

    return None


def _es_combo(nombre, descripcion):
    """Detecta si un producto es un combo/kit/pack/lote."""
    texto = f"{nombre} {descripcion}".lower()
    patrones = [
        r'\bcombo\b', r'\bkit\b', r'\bpack\b', r'\blote\b',
        r'\bpromo\b', r'\b x \d+\b', r'\bmultipack\b',
        r'^\d+\s*(unid|u|und|unidades)\s', r'\bx\d+\s*(unid|u|und)?\s*$',
        r'\bpaquete\s*(de\s*)?\d+\b', r'\b(2|3|4|5|6|10)\s*(en\s*)?1\b',
    ]
    for p in patrones:
        if re.search(p, texto):
            return True
    return False


def _es_duplicado(nombre):
    """Verifica si ya existe un producto con nombre similar."""
    import db
    existentes = db.get_productos()
    # Normalizar nombre candidato
    import unicodedata
    def norm(s):
        s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii').lower().strip()
        return re.sub(r'[^\w\s]', '', s)
    nom_norm = norm(nombre)
    for e in existentes:
        if norm(e["nombre"]) == nom_norm:
            return True, e["id"]
        # Check if candidate name is substring of existing or vice versa
        if len(nom_norm) > 8 and (nom_norm in norm(e["nombre"]) or norm(e["nombre"]) in nom_norm):
            return True, e["id"]
    return False, None


def _buscar_imagenes_en_txt(ruta_txt, carpeta_media):
    """
    Busca las imágenes mencionadas en el TXT y extrae las
    descripciones del mismo mensaje (imagen + texto adjunto).
    Detecta: (archivo adjunto), .jpg, .png, <Media omitted>, IMG-*
    """
    mensajes = _parsear_whatsapp_texto(ruta_txt)
    candidatos = []
    patron_imagen = re.compile(
        r"(\(archivo adjunto\)|<multimedia omitido>|<Media omitted>|\.(jpg|jpeg|png|webp)|IMG-\d+)",
        re.IGNORECASE,
    )
    remitentes_principales = [
        "franco", "matías", "pm importados", "distribuidora",
        "mayorista", "fabrica", "oficial",
    ]

    for i, msg in enumerate(mensajes):
        texto = msg["texto"]
        es_imagen = bool(patron_imagen.search(texto))
        if not es_imagen:
            continue

        # Extraer nombre real del archivo de imagen
        nombre_archivo = _extraer_nombre_archivo_imagen(texto)

        # Limpiar el texto: sacar nombre de archivo y "(archivo adjunto)"
        descripcion = re.sub(
            r"[\u200e]?(?:IMG|VID|PTT|STK)-\S+\.\w+\s*\(archivo adjunto\)\s*",
            "", texto, flags=re.IGNORECASE,
        )
        descripcion = re.sub(
            r"<multimedia omitido>\s*", "", descripcion, flags=re.IGNORECASE,
        )
        descripcion = descripcion.strip().strip("*").strip()

        # Si después de limpiar no queda texto, buscar alrededor
        if not descripcion:
            for j in range(max(0, i - 2), i):
                txt = mensajes[j]["texto"]
                if not patron_imagen.search(txt) and not any(
                    x in txt.lower() for x in ["se unió", "creó el grupo", "cifrados"]
                ):
                    descripcion = txt
                    break
            if not descripcion and i + 1 < len(mensajes):
                txt = mensajes[i + 1]["texto"]
                if not patron_imagen.search(txt) and not any(
                    x in txt.lower() for x in ["se unió", "creó el grupo", "cifrados"]
                ):
                    descripcion = txt

        # Extraer precio de la descripción o del texto completo
        texto_completo = descripcion or texto
        texto_crudo = msg["texto"]
        precio = _extraer_precio(texto_crudo) or _extraer_precio(texto_completo)

        # Nombre sugerido: primera línea o frase relevante
        nombre_sugerido = _extraer_nombre_producto(texto_completo) if texto_completo else "Producto"

        remitente_lower = msg["remitente"].lower()
        es_principal = any(r in remitente_lower for r in remitentes_principales)

        candidatos.append({
            "remitente": msg["remitente"],
            "descripcion": texto_completo,
            "nombre_sugerido": nombre_sugerido,
            "precio": precio,
            "es_principal": es_principal,
            "timestamp": msg["timestamp"],
            "archivo_imagen": nombre_archivo,
        })

    return candidatos


def _extraer_nombre_producto(descripcion):
    """Extrae el nombre del producto de la descripción.

    Busca la línea con más contenido descriptivo (evita marketing,
    precios, y líneas con solo emojis/símbolos).
    """
    if not descripcion:
        return "Producto"

    import unicodedata

    def _tiene_letras(t):
        return any(c.isalpha() for c in t)

    def _es_linea_comercial(t):
        """Detecta líneas que son puro marketing o precios."""
        bajos = t.lower().strip()
        patrones_comerciales = [
            r'^[\d\s.$%/+\-*|:;\u200e\u200f\(\)\[\]]+$',
            r'^precio', r'^unidad', r'^unidades', r'^envío',
            r'^consultar', r'^aprovecha', r'^stockeate',
            r'^promo', r'^especial', r'^ideal para',
            r'^\*[\d\s.$%]+\*$',
        ]
        for p in patrones_comerciales:
            if re.search(p, bajos):
                return True
        # Más de 60% de caracteres no-letra → probablemente no es nombre
        if len(t) > 5:
            letras = sum(1 for c in t if c.isalpha())
            if letras / len(t) < 0.3:
                return True
        return False

    # Normalizar saltos de línea y asteriscos
    lineas = descripcion.replace("\r", "").split("\n")
    candidatas = []
    for linea in lineas:
        limpia = linea.strip("* \t\u200e\u200f").strip()
        if not limpia or len(limpia) < 4:
            continue
        # Quitar emojis para evaluar el contenido real
        solo_texto = ''.join(c for c in limpia if c.isascii() and (c.isalnum() or c in ' /-.,()'))
        solo_texto = solo_texto.strip()
        if not _tiene_letras(solo_texto):
            continue
        if _es_linea_comercial(solo_texto):
            continue
        # Puntaje: más letras = mejor nombre
        letras = sum(1 for c in solo_texto if c.isalpha())
        candidatas.append((letras, limpia))

    if not candidatas:
        # Fallback: primer texto con letras
        for linea in lineas:
            limpia = linea.strip("* \t\u200e\u200f").strip()
            if _tiene_letras(limpia):
                candidatas.append((0, limpia))
                break

    candidatas.sort(key=lambda x: -x[0])
    mejor = candidatas[0][1] if candidatas else "Producto"
    # Limpiar emojis/símbolos sobrantes
    mejor = re.sub(r'[^\w\s/\-,.()áéíóúñÁÉÍÓÚÑ]', '', mejor).strip()
    mejor = re.sub(r'\s+', ' ', mejor).strip()
    return mejor[:80] if mejor else "Producto"


def _coincidir_imagenes(candidatos, imagenes_copiadas):
    """Asigna imágenes copiadas a candidatos por nombre de archivo original."""
    for c in candidatos:
        c["imagen_copiada"] = None
    if not imagenes_copiadas:
        return

    # Build mapping: original IMG filename → dest path
    img_map = {}
    for img in imagenes_copiadas:
        img_map[img["original"]] = img["destino"]

    for c in candidatos:
        archivo = c.get("archivo_imagen")
        if archivo and archivo in img_map:
            c["imagen_copiada"] = img_map[archivo]

    # For remaining candidates without match, assign sequentially
    sin_asignar = [c for c in candidatos if c["imagen_copiada"] is None]
    sin_mapa = [img["destino"] for img in imagenes_copiadas
                if img["destino"] not in {c["imagen_copiada"] for c in candidatos if c["imagen_copiada"]}]
    for i, c in enumerate(sin_asignar):
        if i < len(sin_mapa):
            c["imagen_copiada"] = sin_mapa[i]


def importar_desde_txt(proveedor, archivo_txt=None):
    """
    Importa productos desde un archivo de exportación de WhatsApp.
    - proveedor: nombre del proveedor (se crea si no existe)
    - archivo_txt: nombre del archivo en data/whatsapp_export/
                   Si es None, usa el primer .txt encontrado.

    Retorna lista de dicts con productos sugeridos (no guardados).
    """
    if archivo_txt:
        ruta_txt = os.path.join(EXPORT_DIR, archivo_txt)
    else:
        txts = _listar_archivos_txt()
        if not txts:
            raise FileNotFoundError(
                f"No hay archivos .txt en {EXPORT_DIR}/. "
                "Exportá un chat de WhatsApp con medios y ponelo ahí."
            )
        ruta_txt = os.path.join(EXPORT_DIR, txts[0])

    if not os.path.exists(ruta_txt):
        raise FileNotFoundError(f"No se encuentra {ruta_txt}")

    # Buscar carpeta de medios (WhatsApp exporta una carpeta con el mismo nombre)
    base = os.path.splitext(ruta_txt)[0]
    carpeta_media = base
    if not os.path.isdir(carpeta_media):
        carpeta_media = os.path.join(EXPORT_DIR, f"{os.path.basename(base)}_archivos")
    if not os.path.isdir(carpeta_media):
        carpeta_media = os.path.dirname(ruta_txt)

    candidatos = _buscar_imagenes_en_txt(ruta_txt, carpeta_media)

    # Copiar imágenes si hay carpeta de medios
    imagenes_copiadas = []
    if carpeta_media and os.path.isdir(carpeta_media):
        imagenes = sorted([
            f for f in os.listdir(carpeta_media)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            and os.path.isfile(os.path.join(carpeta_media, f))
        ])
        dest_dir = os.path.join(IMAGENES_DIR, proveedor)
        os.makedirs(dest_dir, exist_ok=True)
        for idx, img in enumerate(imagenes):
            src = os.path.join(carpeta_media, img)
            nuevo_nombre = _normalizar_nombre_archivo(img, proveedor, idx + 1)
            dst = os.path.join(dest_dir, nuevo_nombre)
            shutil.copy2(src, dst)
            imagenes_copiadas.append({"original": img, "destino": dst})

    _coincidir_imagenes(candidatos, imagenes_copiadas)

    return {
        "proveedor": proveedor,
        "archivo": ruta_txt,
        "candidatos": candidatos,
        "imagenes_copiadas": imagenes_copiadas,
    }


def auto_crear_productos(resultado, margen=35):
    """
    Crea productos automáticamente desde el resultado de importar_desde_txt.
    - resultado: dict de importar_desde_txt
    - margen: margen de ganancia deseado (default 35%)

    Retorna dict con: creados, saltados, errores
    """
    import db
    import precios as pcalc

    proveedor = resultado["proveedor"]
    candidatos = resultado["candidatos"]
    creados = []
    saltados = []
    errores = []

    # Get or create provider
    proveedores = db.get_proveedores()
    prv = next((p for p in proveedores if p["nombre"].lower() == proveedor.lower()), None)
    if not prv:
        pid = db.add_proveedor(proveedor)
        if not pid:
            return {"creados": [], "saltados": [], "errores": [f"No se pudo crear proveedor '{proveedor}'"]}
        prv = {"id": pid}

    for c in candidatos:
        nombre = c["nombre_sugerido"]
        if not nombre or nombre == "Producto":
            saltados.append({"candidato": c, "motivo": "Sin nombre"})
            continue

        # Skip combos
        if _es_combo(nombre, c.get("descripcion", "")):
            saltados.append({"candidato": c, "motivo": f"Es combo/kit: {nombre}"})
            continue

        # Skip duplicates
        dup, dup_id = _es_duplicado(nombre)
        if dup:
            saltados.append({"candidato": c, "motivo": f"Ya existe (ID {dup_id}): {nombre}"})
            continue

        costo = c.get("precio")
        if not costo or costo <= 0:
            saltados.append({"candidato": c, "motivo": f"Sin precio de costo ({nombre})"})
            continue

        # Extract USD price
        texto_crudo = c.get("descripcion", "") or ""
        costo_usd = _extraer_precio_usd(texto_crudo) or 0

        try:
            # Create product
            pid = db.add_producto(
                nombre=nombre[:60],
                descripcion=c["descripcion"][:500] if c["descripcion"] else "",
                proveedor_id=prv["id"],
                costo=costo,
                stock=1,
            )

            # Set USD price if found
            if costo_usd:
                db.update_producto(pid, costo_usd=costo_usd)
                # Calculate final price from USD
                resultado_precio = pcalc.calcular_precio_desde_usd(costo_usd, margen)
                db.update_producto(pid,
                                   precio_venta=resultado_precio["precio_final"],
                                   margen_porcentaje=resultado_precio["margen_porcentaje"])
            else:
                # Fallback: calculate from ARS cost
                params = pcalc.ParametrosPrecio(
                    costo=costo,
                    margen_deseado=margen,
                )
                resultado_precio = pcalc.calcular_precio_final(params)
                if "error" not in resultado_precio:
                    db.update_producto(pid,
                                       precio_venta=resultado_precio["precio_final"],
                                       margen_porcentaje=resultado_precio["margen_porcentaje"])

            # Link image
            img_path = c.get("imagen_copiada")
            if img_path:
                rel_path = os.path.relpath(img_path, BASE_DIR)
                db.add_imagen(pid, rel_path, es_principal=True)

            creados.append({
                "id": pid,
                "nombre": nombre,
                "costo": costo,
                "costo_usd": costo_usd,
                "precio_venta": resultado_precio.get("precio_final", 0),
                "imagen": bool(img_path),
            })

        except Exception as e:
            errores.append({"candidato": c, "motivo": str(e)})

    return {"creados": creados, "saltados": saltados, "errores": errores}


def escanear_carpeta_imagenes(proveedor):
    """
    Escanea una carpeta de imágenes de un proveedor y propone productos.
    """
    carpeta = os.path.join(IMAGENES_DIR, proveedor)
    if not os.path.isdir(carpeta):
        return []

    archivos = sorted([f for f in os.listdir(carpeta)
                       if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))])
    productos = []
    for f in archivos:
        nombre = os.path.splitext(f)[0].replace("_", " ").replace("-", " ").title()
        productos.append({
            "archivo": os.path.join(carpeta, f),
            "nombre_sugerido": nombre,
            "descripcion": "",
        })
    return productos
