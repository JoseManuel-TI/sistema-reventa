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
        [13/6/26, 3:23:25 p. m.] Nombre: texto   (iPhone export)
        [14/1/2024 10:30:45] Juan: texto         (Android / iPhone sin AM/PM)
        13/6/2026, 15:14 - Juan: texto           (Android nuevo)
    Retorna lista de dicts con: timestamp, remitente, texto
    """
    # AM/PM marker: \u202f (thin space) + [ap] + . + \u202f + m + .
    ampm = '\u202f[ap]\\.\u202fm\\.'
    # Modern format: no brackets, separated by " - "
    patron_moderno = re.compile(
        rf"\u200e?(\d{{1,2}}/\d{{1,2}}/\d{{2,4}},\s*\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:{ampm})?)\s*-\s*([^:]+?)\s*:\s*(.*)"
    )
    # Old format / iPhone export: [timestamp] with brackets
    patron_antiguo = re.compile(
        rf"\u200e?\[(\d{{1,2}}/\d{{1,2}}/\d{{2,4}},\s*\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:{ampm})?)\]\s*([^:]+?)\s*:\s*(.*)"
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
    """Extrae precio en USD de un texto. Busca formatos como USD 20, 20 USD, U$D 20, usd 20."""
    texto_limpio = texto.replace("*", "").replace("_", "").strip()
    texto_limpio = re.sub(r"[\u200e\u200f]", "", texto_limpio)

    # Formato: "120 USD" (número antes de USD)
    m = re.search(r'([\d]{1,3}(?:[.,][\d]{3})*(?:[.,]\d+)?)\s*(?:USD|U\$S?|usd|dolar|dólar)', texto_limpio, re.IGNORECASE)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass

    # Formato: "USD 20" (USD antes del número)
    m = re.search(r'(?:USD|U\$S?|usd)\s*:?\s*([\d]{1,3}(?:[.,][\d]{3})*(?:[.,]\d+)?)', texto_limpio, re.IGNORECASE)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass

    return None


def _es_combo(nombre, descripcion):
    """Detecta si un producto es un combo/kit/pack de multiples items."""
    texto = f"{nombre[:60]}".lower()
    texto_completo = f"{descripcion[:500]}".lower() if descripcion else ""

    if re.search(r'^(combo|kit|pack|lote)\b', texto):
        return True
    if re.search(r'\b(combo|multipack)\b', texto):
        return True
    if re.search(r'\b(2|3|4|5|6|10)\s*(en\s*)?1\b', texto):
        return True
    if re.search(r'\b(incluye|incluido)\s+\d+\s+', texto):
        return True
    # Multiple items: "1 Celular X + 1 Tablet Y", "2 Adaptadores 2 Charger"
    if re.search(r'^\d+\s+\w+\s+.*\d+\s+\w+', texto):
        return True
    # Also: "Manguera 15 Mts 1 Set..." (word + number + word + number)
    if re.search(r'\w+\s+\d+\s+\w+\s+\d+\s+\w+', texto):
        return True
    if re.search(r'\b(total|precio\s+por\s+cantidad)\b', texto) and re.search(r'\b(unidades?|c/u)\b', texto):
        return True
    if re.search(r'\d+\s+unidad(es)?\s+\d+', texto):
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
    Soporta formatos Android (IMG-*, (archivo adjunto)) e iPhone (imagen omitida, PHOTO-*).
    """
    mensajes = _parsear_whatsapp_texto(ruta_txt)
    candidatos = []
    patron_imagen = re.compile(
        r"(\(archivo adjunto\)|<multimedia omitido>|<Media omitted>|\.(jpg|jpeg|png|webp)|IMG-\d+|imagen omitida)",
        re.IGNORECASE,
    )
    remitentes_principales = [
        "franco", "matías", "pm importados", "distribuidora",
        "mayorista", "fabrica", "oficial",
    ]

    # Scan ALL media files sorted alphabetically (this matches the order they
    # appear in the chat export). Extract PHOTO files in their correct sequence.
    photos_in_order = []
    if carpeta_media and os.path.isdir(carpeta_media):
        all_media = sorted([
            f for f in os.listdir(carpeta_media) if os.path.isfile(os.path.join(carpeta_media, f))
        ])
        for f in all_media:
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                photos_in_order.append(f)

    photo_idx = 0

    for i, msg in enumerate(mensajes):
        texto = msg["texto"]
        es_imagen = bool(patron_imagen.search(texto))
        if not es_imagen:
            continue

        remitente_lower = msg["remitente"].lower()
        es_principal = any(r in remitente_lower for r in remitentes_principales)

        # Solo procesar mensajes del vendedor principal
        if not es_principal:
            continue

        # iPhone export: "imagen omitida" - assign PHOTO files by media sequence order
        es_iphone = "imagen omitida" in texto.lower()

        # Limpiar el texto: sacar nombre de archivo y "(archivo adjunto)"
        descripcion = re.sub(
            r"[\u200e]?(?:IMG|VID|PTT|STK)-\S+\.\w+\s*\(archivo adjunto\)\s*",
            "", texto, flags=re.IGNORECASE,
        )
        descripcion = re.sub(
            r"<multimedia omitido>\s*", "", descripcion, flags=re.IGNORECASE,
        )
        descripcion = descripcion.replace("imagen omitida", "").strip()
        descripcion = descripcion.strip("* \t\u200e\u200f").strip()

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

        # Extract suggested name FIRST to decide if we should consume a photo
        texto_completo = descripcion or texto
        texto_crudo = msg["texto"]
        nombre_sugerido = _extraer_nombre_producto(texto_completo) if texto_completo else "Producto"

        # Only assign image if this message is likely a valid product
        # (skip combos and invalid names so images aren't wasted on filtered items)
        nombre_archivo = None
        es_valido = (
            _es_nombre_valido(nombre_sugerido)
            and not _es_combo(nombre_sugerido, texto_completo)
        )

        if es_iphone and es_valido and photos_in_order:
            if photo_idx < len(photos_in_order):
                nombre_archivo = photos_in_order[photo_idx]
                photo_idx += 1
        elif not es_iphone:
            nombre_archivo = _extraer_nombre_archivo_imagen(texto)

        # Extract price
        precio = _extraer_precio(texto_crudo) or _extraer_precio(texto_completo)

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
    """Extrae el nombre del producto de la descripción buscando marcas y modelos."""
    if not descripcion:
        return "Producto"

    # Split by * (bold markers) or newlines
    partes = re.split(r'[\n*]+', descripcion)
    
    # Known brands to look for
    brands = r'(samsung|xiaomi|redmi|poco|apple|jbl|lg|tcl|bgh|gadnic|nuvoh|hisense|noga|winco|phonix|siera|noblex|philco|atvio|hyundai|telefunken|pioneer|embassy|saho|force\s*by\s*gadnic|daihatsu|lamborghini|cecotec|ken\s*brown|n[oó]made|enova|hynurik|kalley|supreme|geek\s*bar|vapear|sprint|hal[oó]gena|stromberg|pro\s*bass|akro|karseell|elfbar|canon|atma|lusqtoff)'
    
    mejor_candidata = ""
    mejor_puntaje = -1
    
    for p in partes:
        p = p.strip("* \t\u200e\u200f\r\n").strip()
        if not p or len(p) < 4:
            continue
        
        limpio = re.sub(r'[^\w\s/\-,.()]', ' ', p)
        limpio = re.sub(r'\s+', ' ', limpio).strip()
        if not limpio or len(limpio) < 4:
            continue
        
        p_lower = limpio.lower()
        
        if re.match(r'^[\d\s.$%,/()]+$', limpio.replace('pesos', '').replace('usd', '')):
            continue
        
        brand_match = re.search(brands, p_lower)
        
        puntaje = len(limpio)
        if brand_match:
            puntaje += 20
        if re.search(r'\b(tv|smart|celular|notebook|parlante|auricular|proyector|cafetera|estufa|freidora|monopat[ní]n|bicicleta|tablet|microondas|aire\s*aacondicionado|inflador|lavarropas|sill[oa]n|cocina|m[áa]quina|c[áa]mara|impresora|pava|volante)\b', p_lower, re.IGNORECASE):
            puntaje += 10
        
        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            mejor_candidata = limpio
    
    if mejor_candidata:
        return _limpiar_nombre(mejor_candidata)
    
    for p in partes:
        p = p.strip("* \t\u200e\u200f").strip()
        if re.search(brands, p.lower()):
            limpio = re.sub(r'[^\w\s/\-,.()]', ' ', p)
            limpio = re.sub(r'\s+', ' ', limpio).strip()
            return _limpiar_nombre(limpio)
    
    return "Producto"


def _limpiar_nombre(nombre):
    """Limpia el nombre del producto para mostrar en catálogo, sin texto marketing."""
    import unicodedata
    n = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode('ascii').strip()
    n = re.sub(r'\(.*?\)', ' ', n)
    n = re.sub(r'[^\w\s/\-]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()

    prefijos = [
        r'^ultimas?\s+unidades?\s+', r'^ultima?\s+unidad\s+',
        r'^no\s+reingresan\s+', r'^promo\s+\w+\s+',
        r'^reingres[oa]\s+', r'^super\s+(reba|liquidacion|promocion|oferta|precio)\s+',
        r'^(gran\s+)?liquidacion\s+', r'^preventa\s+',
        r'^aprovech[ae]\s+', r'^solo\s+',
        r'^nuevos?\s+ingresos?\s+', r'^nuevo\s+',
        r'^ideal\s+(para\s+)?', r'^equipa\s+', r'^arma\s+', r'^renova\s+',
        r'^disponibles?\s+', r'^sale\s+',
        r'^pocas?\s+unidades\s+', r'^d[ei]l?\s+',
        r'^rebaja\s+(de\s+)?precios?\s+', r'^por\s+', r'^solo\s+por\s+',
        r'^porque\s+', r'^emprendedor\s+', r'^et\s+', r'^dummy\s+',
        r'^hot\s+sale\s+', r'^mundial\s+', r'^unica\s+unidad\s+',
        r'^en\s+stock\s+', r'^con\s+env[ií]o\s+gratis\s*',
        r'^stock\s+limitado\s*', r'^consult[aá]\s+', r'^ped[ií]',
        r'^hac[eé]\s+tu\s+pedido\s*', r'^env[ií]os?\s*',
        r'^bajaron\s+los\s+precios\s+',
        r'^añade\s+un\s+comentario\s+',
        r'^cada\s+unidad\s+[\d\s.,]+\s+',
        r'^ultimos\s+d[ií]as?\s+con\s+este\s+',
        r'^escrib[ei]me?\s+(al|por)\s+(el\s+)?privado\s+',
        r'^hacemos\s+env[ií]os?\s+',
        r'^s[aá]bado\s+',
        r'^eleg[ií]\s+(los\s+)?equipos?\s+',
        r'^al\s+costo\s+',
        r'^(el\s+)?producto\s+mas\s+pedido\s+',
        r'^el\s+hogar\s+',
        r'^jardin\s+eventos\s+',
        r'^cada\s+unidad\s+[\d\s.,]+\s+',
    ]
    for _ in range(3):
        for p in prefijos:
            n = re.sub(p, '', n, flags=re.IGNORECASE).strip()

    n = re.sub(r'(precios?\s+(especiales?\s+)?(mayoristas?)?'
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
               r'|el\s+regalo\s+perfecto|la\s+mejor\s+opcion'
               r'|hace\s+tu\s+pedido|disfruta\s+cafe'
               r'|solo\s+\d+\s+unidades|pro\s+bass'
               r'|precios\s+mayorist|calidad\s+premium'
               r'|excelente\s+salida|stockeate|stockear'
               r'|aprovecha|aproveche|renova\s+tu'
               r'|convierta|converti'
               r'|ideal\s+(para\s+)?(eventos|locales|disfrutar|uso|dejar)'
               r'|disfruta\s+tus|todo\s+lo\s+que\s+necesitas'
               r'|la\s+mejor\s+experiencia|unica\s+unidad\s+disponible'
               r'|copa\s+del\s+mundo|regalar\s+este\s+domingo'
               r'|precio\s+promo|precio\s+especial)'
               r'\s+.*$', '', n, flags=re.IGNORECASE)
    
    for pat in [
        r'\b(precios?\s+(especiales?\s+)?(mayoristas?)?|precio\s+(especial|promo)|consultanos|escribinos|envio\s+gratis|ultimas\s+unidades|disponibles?|no\s+reingresan'
        r'|precios?\s+por\s+cantidad|con\s+detalle\s+en\s+pantalla|podes\s+elegir\s+el\s+que\s+quieras'
        r'|cod\s+av\d+|de\s+almacenamiento)\s*(.*)?$',
    ]:
        n = re.sub(pat, ' ', n, flags=re.IGNORECASE).strip()
    # Strip everything after "precios", "promo", "especial" when followed by text
    n = re.sub(r'\s+(precios?\s+especial(es)?\s+.*|promo\s+\w+\s+.*)$', ' ', n, flags=re.IGNORECASE).strip()
    # Strip trailing numbers that are clearly prices (have $, USD, or long number sequences)
    n = re.sub(r'\s+\$?[\d]{4,}[\s\d.$%/]*\s*$', ' ', n).strip()
    n = re.sub(r'\s+[\d]{2,3}([.,]\d+)?\s*(usd|dolares?)\s*$', ' ', n, flags=re.IGNORECASE).strip()
    n = re.sub(r'\s+usd\s+\$?[\d\s.,]+\s*$', ' ', n, flags=re.IGNORECASE).strip()
    n = re.sub(r'^\d[\d\s.$%/]*\s+', ' ', n).strip()
    n = re.sub(r'\$[\d\s.,]+(\s*usd)?', ' ', n, flags=re.IGNORECASE)
    n = re.sub(r'[\d]{2,3}([.,]\d+)?\s*(usd|dolares?)', ' ', n, flags=re.IGNORECASE)
    n = re.sub(r'(usd|dolares?)\s*[\d\s.,]+', ' ', n, flags=re.IGNORECASE)
    n = re.sub(r's/\s+', ' / ', n)
    n = re.sub(r'\s+', ' ', n).strip().rstrip(',').strip()

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


def _es_nombre_valido(nombre):
    """Verifica si el nombre extraído corresponde realmente a un producto."""
    if not nombre or len(nombre) < 5:
        return False
    genericos = [
        'a todo el pais', 'envio', 'consultar', 'escribinos',
        'pedilo', 'hace tu pedido', 'melo por privado', 'hablame',
        'regalar', 'diseno moderno', 'capacidad', 'cada unidad',
        'ultimos dias', 'sabado', 'elegi los equipos', 'hacemos envios',
        'precio especial', 'disponibles', 'stock limitado',
        'aprovecha', 'aproveche', 'preventa', 'tu cine en casa',
        'el hogar', 'jardin eventos', 'al costo', 'producto mas pedido',
        'superando los', 'incluye ', 'incluido',
        'pedi el tuyo', 'ferias y camping', 'taller o reventa',
        'parlantes surtidos', 'cafetera prensa francesa',
    ]
    nl = nombre.lower()
    for g in genericos:
        if g in nl:
            return False
    if re.match(r'^[\d\s.,/()]+$', nombre):
        return False
    if nombre.strip() in ('y', 'e', 'o', 'a', 'con', 'de', 'del', 'por', 'para', 'solo', 'ahora', 'este', 'esta'):
        return False
    words = nombre.split()
    if len(words) <= 1 and len(words[0]) < 5:
        return False
    return True


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

        # Skip invalid/generic names
        if not _es_nombre_valido(nombre):
            saltados.append({"candidato": c, "motivo": f"Nombre inválido: {nombre}"})
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
            "archivo": os.path.relpath(os.path.join(carpeta, f), BASE_DIR),
            "nombre_sugerido": nombre,
            "descripcion": "",
        })
    return productos
