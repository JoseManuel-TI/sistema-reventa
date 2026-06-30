"""
Auto-importador de productos desde WhatsApp.

Uso:
  python scripts/autoimport.py                     # una ejecucion
  python scripts/autoimport.py --watch             # loop cada 60s
  python scripts/autoimport.py --interval 300      # cada 5 min
  python scripts/autoimport.py --margen 40         # margen 40%

State file: data/import_state.json
"""

import os
import re
import sys
import json
import time
import shutil
import unicodedata
import sqlite3
import argparse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

EXPORT_DIR = os.path.join(BASE_DIR, "data", "whatsapp_export")
IMAGENES_DIR = os.path.join(BASE_DIR, "imagenes", "proveedores")
STATE_FILE = os.path.join(BASE_DIR, "data", "import_state.json")
DB_PATH = os.path.join(BASE_DIR, "data", "productos.db")

# ─── importar_whatsapp functions (copied to keep self-contained) ───

def _parsear_whatsapp_texto(ruta_txt):
    # Android modern:  "6/26/26, 3:23:25 p. m. - Name: text"
    patron_moderno = re.compile(
        r"\u200e?(\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}(?::\d{2})?(?: [ap]\. m\.)?)\s*-\s*([^:]+):\s*(.*)"
    )
    # Antiguo con AM/PM: "[13/6/26, 4:38:24 p. m.] ~ Name: text"
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
                mensajes.append({
                    "timestamp": m.group(1).strip(),
                    "remitente": m.group(2).strip(),
                    "texto": m.group(3).strip(),
                })
            elif mensajes:
                mensajes[-1]["texto"] += " " + linea
    return mensajes


def _extraer_nombre_archivo_imagen(texto):
    m = re.search(r"(IMG-\S+\.\w+)", texto, re.IGNORECASE)
    return m.group(1) if m else None


def _extraer_precio(texto):
    texto_limpio = texto.replace("*", "").replace("_", "").strip()
    texto_limpio = re.sub(r"[\u200e\u200f]", "", texto_limpio)
    m = re.search(r'\$\s*([\d]{1,3}(?:\.[\d]{3})*(?:[\.,]\d+)?)', texto_limpio)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass
    m = re.search(r'USD\s*[|/]\s*\$\s*([\d]{1,3}(?:\.[\d]{3})*(?:[\.,]\d+)?)', texto_limpio)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass
    m = re.search(r'(?<!\w)([\d]{2,3}(?:\.[\d]{3})+(?:[\.,]\d+)?)\s*$', texto_limpio)
    if m:
        val = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(val)
        except ValueError:
            pass
    return None


def _extraer_nombre_producto(descripcion):
    if not descripcion:
        return "Producto"
    import unicodedata
    def _tiene_letras(t):
        return any(c.isalpha() for c in t)
    def _es_linea_comercial(t):
        bajos = t.lower().strip()
        patrones = [
            r'^[\d\s.$%/+\-*|:;\u200e\u200f\(\)\[\]]+$',
            r'^precio', r'^unidad', r'^unidades', r'^envío',
            r'^consultar', r'^aprovecha', r'^stockeate',
            r'^promo', r'^especial', r'^ideal para',
            r'^\*[\d\s.$%]+\*$',
        ]
        for p in patrones:
            if re.search(p, bajos):
                return True
        if len(t) > 5:
            letras = sum(1 for c in t if c.isalpha())
            if letras / len(t) < 0.3:
                return True
        return False
    lineas = descripcion.replace("\r", "").split("\n")
    candidatas = []
    for linea in lineas:
        limpia = linea.strip("* \t\u200e\u200f").strip()
        if not limpia or len(limpia) < 4:
            continue
        solo_texto = ''.join(c for c in limpia if c.isascii() and (c.isalnum() or c in ' /-.,()'))
        solo_texto = solo_texto.strip()
        if not _tiene_letras(solo_texto):
            continue
        if _es_linea_comercial(solo_texto):
            continue
        letras = sum(1 for c in solo_texto if c.isalpha())
        candidatas.append((letras, limpia))
    if not candidatas:
        for linea in lineas:
            limpia = linea.strip("* \t\u200e\u200f").strip()
            if _tiene_letras(limpia):
                candidatas.append((0, limpia))
                break
    candidatas.sort(key=lambda x: -x[0])
    mejor = candidatas[0][1] if candidatas else "Producto"
    mejor = re.sub(r'[^\w\s/\-,.()áéíóúñÁÉÍÓÚÑ]', '', mejor).strip()
    mejor = re.sub(r'\s+', ' ', mejor).strip()
    return mejor[:80] if mejor else "Producto"


def extraer_imagen_desde_carpeta(ruta_txt, carpeta_media, proveedor):
    """Copia imagenes de la carpeta media y retorna lista de {original, destino}.
    Solo procesa imagenes modificadas dentro de las 2h posteriores al .txt
    para evitar asignar fotos de exportaciones anteriores.
    """
    imagenes_copiadas = []
    if not carpeta_media or not os.path.isdir(carpeta_media):
        return imagenes_copiadas
    txt_mtime = os.path.getmtime(ruta_txt) if os.path.exists(ruta_txt) else 0
    imagenes = sorted([
        f for f in os.listdir(carpeta_media)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        and os.path.isfile(os.path.join(carpeta_media, f))
        and (txt_mtime == 0 or abs(os.path.getmtime(os.path.join(carpeta_media, f)) - txt_mtime) < 7200)
    ])
    dest_dir = os.path.join(IMAGENES_DIR, proveedor)
    os.makedirs(dest_dir, exist_ok=True)
    for idx, img in enumerate(imagenes):
        src = os.path.join(carpeta_media, img)
        ext = os.path.splitext(img)[1].lower()
        fecha = datetime.now().strftime("%Y%m%d")
        nuevo_nombre = f"{proveedor}_{idx+1:03d}_{fecha}{ext}"
        dst = os.path.join(dest_dir, nuevo_nombre)
        shutil.copy2(src, dst)
        imagenes_copiadas.append({"original": img, "destino": os.path.relpath(dst, BASE_DIR)})
    return imagenes_copiadas


def _tiene_identidad_producto(nombre):
    """True si el nombre parece un producto real (no solo marketing text)."""
    bajos = _quitar_acentos(nombre).lower().strip()
    for p in [
        r'^reingreso\s+dummy\b', r'^super\s+liquidacion\b',
        r'^super\s+rebaja\b', r'^liquidacion\s+de\s+ultimas',
        r'^ultima\s+en\s+stock\b', r'^ultimas\s+disponibles\b',
        r'^ideal\s+para\s+regalar\b', r'^ultimas\s+unidades\s*$',
        r'^reingreso\s+(geek|jbl)',  # these are OK (have brand)
    ]:
        if re.search(p, bajos):
            return False
    
    # Check if name contains a known brand or product word
    product_words = r'\b(samsung|xiaomi|redmi|poco|jbl|lg|tcl|bgh|gadnic|nuvoh|nomade|siera|enova|noga|pioneer|winco|daihatsu|lamborghini|hyundai|hisense|philco|cecotec|geek|supreme|ovns|xbox|nurik|kalley|vape|airpods|galaxy|proyector|notebook|bicicleta|sillon|freidora|cava|cafeter|parlante|auricular|volante|silla|pava|estufa|teclado|mouse|tender|monopatin|crema|tostadora|pochoclera|cargador|cable|adaptador|televisor|smart)\b'
    if re.search(product_words, bajos):
        return True
    
    # Has a model number pattern (like A15, C75, 4K, 256GB, etc.)
    if re.search(r'\b([A-Z]\d{2,}|[A-Z]+\d+[A-Za-z]*|\d+[Kk]|[\d]+GB)\b', nombre):
        return True
    
    # If it has a recognizable product category word
    category_words = r'\b(tv|tvs|smart|wifi|bluetooth|camara|control|bicicleta|monopatin|freidora|microondas|lavarropas|heladera|ventilador|calefactor|aire|zapatilla|remera|pantalon|buzo|campera|mochila|reloj|pulsera|lente|gafas)\b'
    if re.search(category_words, bajos):
        return True
    
    return False


def _limpiar_descripcion(text):
    """Remove wholesale pricing, marketing fluff, WhatsApp metadata from descriptions."""
    if not text:
        return ''
    t = text
    t = re.sub(r'\d{1,2}/\d{1,2}/\d{4},\s*\d{1,2}:\d{2}\s*-\s*\+?[\d\s-]+\s*se\s+unió\s+con\s+el\s+enlace\s+del\s+grupo\.?', '', t)
    t = re.sub(r'\d{1,2}/\d{1,2}/\d{4},\s*\d{1,2}:\d{2}\s*-\s*[^:]+:\s*', '', t)
    t = re.sub(r'\d{1,2}/\d{1,2}/\d{4},\s*\d{1,2}:\d{2}\s*-\s*~?[^:]+', '', t)
    # Remove lines containing price patterns
    lines = t.split('\n')
    clean = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.search(r'(USD|\$\s*\d[\d.,]*(?!\s*[a-zA-Záéíóú]))', s, re.IGNORECASE):
            continue
        if re.search(r'\d+\s*[×xX]\s*\$', s):
            continue
        if re.search(r'\d+\s+unidad(?:es)?', s, re.IGNORECASE):
            continue
        if re.search(r'(PRECIO|MAYORISTA|STOCKEATE|APROVECHA)', s, re.IGNORECASE):
            continue
        clean.append(s)
    t = ' '.join(clean)
    t = re.sub(r'[^\w\sáéíóúñ,.!?\-/:()]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:500]


def _es_producto_individual(nombre):
    """True si el producto es individual (no combo/promo/mega/pack)."""
    patrones_combo = [
        r'^combo\b', r'^promo\b', r'^mega\b', r'^pack\b',
        r'^kit\b', r'^lote\b',
    ]
    bajos = nombre.lower().strip()
    for p in patrones_combo:
        if re.match(p, bajos):
            return False
    return True


def _quitar_acentos(t):
    """Remove unicode accents for matching."""
    return unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode('ascii')


def _normalizar_para_dedup(nombre):
    """Normaliza nombre para comparar con productos existentes."""
    n = _quitar_acentos(nombre).lower().strip()
    n = re.sub(r'\(.*?\)', ' ', n)
    n = re.sub(r'[^\w\s/-]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    for _ in range(3):
        for p in [
            r'^(ultimas?\s+)?unidades?\s+(no\s+)?reingresan?\s+',
            r'^ultima?\s+unidad\b', r'^promo\s+\w+\s+',
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
            r'^rebaja\s+(de\s+)?precios?\s+',
            r'^porque\s+', r'^emprendedor\s+',
            r'^et\s+', r'^dummy\s+',
        ]:
            n = re.sub(p, '', n).strip()
    n = re.sub(r'(precios?\s+(especiales?\s+)?(mayoristas?)?|por\s+unidad|no\s+reingresan|de\s+ultimas?\s+unidades|rebaja\s+de\s+precios|oportunidad\s+unica\s+(para\s+)?(stockearte)?|precio\s+especial|precio\s+por\s+(unidad|cantidad)|precio\s+por\s+tiempo\s+limitado|por\s+tiempo\s+limitado|calidad\s+y\s+precio|vivi\s+una\s+experiencia|facilidades\s+de\s+pago|retiro\s+por|consultanos|escribinos)\s+[\w\s]*(usd\s*[\d\s.,/$%]+)?$', ' ', n)
    n = re.sub(r'\$[\d\s.,]+', ' ', n)
    n = re.sub(r'[\d]{2,3}([.,]\d+)?\s*(usd|dolares?)', ' ', n)
    n = re.sub(r'(usd|dolares?)\s*[\d\s.,]+', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    brands = r'\b(samsung|xiaomi|redmi|poco|jbl|lg|tcl|bgh|gadnic|nuvoh|n[oó]made|siera|enova|hynurik|noga|pioneer|winco|daihatsu|lamborghini|hyundai|hisense|philco|noblex|atvio|ken\s*brown|cecotec|midea|whirlpool|geek\s*bar|supreme|ovns|kalley|vapear|sprint|hal[oó]gena)\b'
    brand_match = re.search(brands, n)
    if brand_match:
        start = brand_match.start()
        clave = n[start:start+80].strip()
    else:
        clave = n[:60].strip()
    clave = re.sub(r'\s+', ' ', clave).strip()
    # Only fall back to full name if no brand was found and key is too short
    if not brand_match and len(clave) < 10:
        clave = nombre.lower()[:50]
    return clave


def _existe_producto(db, nombre_normalizado):
    """Check if a product with similar normalized name exists."""
    productos = db.execute(
        "SELECT id, nombre FROM productos WHERE activo = 1"
    ).fetchall()
    for p in productos:
        exist_norm = _normalizar_para_dedup(p["nombre"] if isinstance(p, dict) else p[1])
        # Exact match
        if exist_norm == nombre_normalizado:
            return p[0] if isinstance(p, (list, tuple)) else p["id"]
        # Partial match: one contains the other (handles overly cleaned names)
        if len(exist_norm) >= 5 and len(nombre_normalizado) >= 5:
            if exist_norm in nombre_normalizado or nombre_normalizado in exist_norm:
                return p[0] if isinstance(p, (list, tuple)) else p["id"]
    return None


# ─── Trend detection ───

try:
    from scripts.trending import score_product, is_trending, TREND_THRESHOLD, format_score
    TRENDING_AVAILABLE = True
except ImportError:
    TRENDING_AVAILABLE = False

# ─── Main logic ───

def cargar_estado():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"archivos": {}}


def guardar_estado(estado):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)


def procesar_archivo(ruta_txt, proveedor, margen, estado):
    """Procesa un archivo .txt de WhatsApp: detecta productos nuevos y los importa."""
    import db as db_module
    import precios as pcalc

    filename = os.path.basename(ruta_txt)
    stat = os.stat(ruta_txt)
    mtime = stat.st_mtime
    size = stat.st_size

    # Check if already processed unchanged
    prev = estado["archivos"].get(filename, {})
    if prev.get("mtime") == mtime and prev.get("size") == size:
        print(f"  ↻ {filename}: sin cambios")
        return 0

    # Get or create provider
    proveedores = db_module.get_proveedores()
    prv = next((p for p in proveedores if p["nombre"].lower() == proveedor.lower()), None)
    if not prv:
        pid = db_module.add_proveedor(proveedor)
        if not pid:
            print(f"  ✗ No se pudo crear proveedor '{proveedor}'")
            return 0
        prv = {"id": pid}

    # Find media folder
    base = os.path.splitext(ruta_txt)[0]
    carpeta_media = base if os.path.isdir(base) else os.path.dirname(ruta_txt)
    alt_dir = os.path.join(EXPORT_DIR, f"{filename}_archivos")
    if os.path.isdir(alt_dir):
        carpeta_media = alt_dir

    # Parse messages
    mensajes = _parsear_whatsapp_texto(ruta_txt)
    print(f"  📄 {filename}: {len(mensajes)} mensajes")

    # Extract product candidates from messages with images
    patron_imagen = re.compile(
        r"(\(archivo adjunto\)|<multimedia omitido>|<Media omitted>|\.(jpg|jpeg|png|webp)|IMG-\d+)",
        re.IGNORECASE,
    )
    candidatos = []
    for i, msg in enumerate(mensajes):
        texto = msg["texto"]
        if not patron_imagen.search(texto):
            continue
        nombre_archivo = _extraer_nombre_archivo_imagen(texto)
        descripcion = re.sub(r"[\u200e]?(?:IMG|VID|PTT|STK)-\S+\.\w+\s*\(archivo adjunto\)\s*", "", texto, flags=re.IGNORECASE)
        descripcion = re.sub(r"<multimedia omitido>\s*", "", descripcion, flags=re.IGNORECASE)
        descripcion = descripcion.strip().strip("*").strip()
        if not descripcion:
            for j in range(max(0, i - 2), i):
                txt = mensajes[j]["texto"]
                if not patron_imagen.search(txt) and not any(x in txt.lower() for x in ["se unio", "creo el grupo", "cifrados"]):
                    descripcion = txt
                    break
            if not descripcion and i + 1 < len(mensajes):
                txt = mensajes[i + 1]["texto"]
                if not patron_imagen.search(txt) and not any(x in txt.lower() for x in ["se unio", "creo el grupo", "cifrados"]):
                    descripcion = txt

        texto_crudo = msg["texto"]
        precio = _extraer_precio(texto_crudo) or _extraer_precio(descripcion)
        nombre_sugerido = _extraer_nombre_producto(descripcion) if descripcion else "Producto"

        candidatos.append({
            "remitente": msg["remitente"],
            "descripcion": descripcion,
            "nombre_sugerido": nombre_sugerido,
            "precio": precio,
            "archivo_imagen": nombre_archivo,
        })

    # Copy images
    imagenes_copiadas = extraer_imagen_desde_carpeta(ruta_txt, carpeta_media, proveedor)

    # Map images to candidates
    img_map = {img["original"]: img["destino"] for img in imagenes_copiadas}
    for c in candidatos:
        c["imagen_copiada"] = img_map.get(c.get("archivo_imagen"))
    sin_asignar = [c for c in candidatos if c["imagen_copiada"] is None]
    sin_mapa = [img["destino"] for img in imagenes_copiadas
                if img["destino"] not in {c["imagen_copiada"] for c in candidatos if c["imagen_copiada"]}]
    for i, c in enumerate(sin_asignar):
        if i < len(sin_mapa):
            c["imagen_copiada"] = sin_mapa[i]

    # Filter and create products
    db_conn = sqlite3.connect(DB_PATH)
    db_conn.row_factory = sqlite3.Row

    creados = 0
    saltados = 0
    trend_mode = getattr(procesar_archivo, 'trend_mode', 'auto')
    trend_threshold = getattr(procesar_archivo, 'trend_threshold', TREND_THRESHOLD)
    list_candidates = getattr(procesar_archivo, 'list_candidates', False)
    
    for c in candidatos:
        nombre_full = c["nombre_sugerido"]
        if not nombre_full or nombre_full == "Producto":
            saltados += 1
            continue

        if not _es_producto_individual(nombre_full):
            saltados += 1
            continue

        # Skip if name is just marketing text (no real product identity)
        if not _tiene_identidad_producto(nombre_full):
            saltados += 1
            continue

        costo = c.get("precio")
        if not costo or costo <= 0:
            saltados += 1
            continue

        # Check if already exists
        norm = _normalizar_para_dedup(nombre_full)
        existente = _existe_producto(db_conn, norm)
        if existente:
            saltados += 1
            continue

        # Trend scoring
        trend_result = None
        if TRENDING_AVAILABLE:
            trend_result = score_product(nombre_full, costo, use_web=False)
            is_trend, _ = is_trending(nombre_full, costo, threshold=trend_threshold)

        if list_candidates:
            line = f"    {'COMBO' if not _es_producto_individual(nombre_full) else 'PROD'} | {nombre_full[:55]:<55} "
            if costo:
                line += f"${costo:>8,.0f} | "
            else:
                line += " Sin precio | "
            if trend_result:
                line += f"Score: {trend_result['total']} "
                if not _es_producto_individual(nombre_full):
                    line += "[COMBO]"
            print(line)
            continue

        if TRENDING_AVAILABLE and trend_mode == 'trending-only':
            if not is_trend:
                if trend_result:
                    print(f"    ⏭ {nombre_full[:50]:<50} Score: {trend_result['total']} → {format_score(trend_result)}")
                else:
                    print(f"    ⏭ {nombre_full[:50]:<50} (debajo del umbral de tendencia)")
                saltados += 1
                continue

        # Truncate name only when creating
        nombre = nombre_full[:80]

        # Create product
        try:
            pid = db_module.add_producto(
                nombre=nombre,
                descripcion=_limpiar_descripcion(c["descripcion"]) if c["descripcion"] else "",
                proveedor_id=prv["id"],
                costo=costo,
                stock=1,
            )

            # Suggest margin based on product type
            if TRENDING_AVAILABLE:
                from scripts.trending import suggest_margen
                margen_ajustado = suggest_margen(nombre)
            else:
                margen_ajustado = margen

            params = pcalc.ParametrosPrecio(costo=costo, margen_deseado=margen_ajustado)
            resultado_precio = pcalc.calcular_precio_final(params)
            if "error" not in resultado_precio:
                db_module.update_producto(
                    pid,
                    precio_venta=resultado_precio["precio_final"],
                    margen_porcentaje=resultado_precio["margen_porcentaje"],
                )

            img_path = c.get("imagen_copiada")
            if img_path:
                db_module.add_imagen(pid, img_path, es_principal=True)

            trend_info = ""
            if trend_result:
                trend_info = f" [Score: {trend_result['total']}]"
            print(f"    ✓ Nuevo: {nombre[:50]} → ${resultado_precio.get('precio_final', 0):,.0f}{trend_info}")
            creados += 1

        except Exception as e:
            print(f"    ✗ Error: {nombre[:40]} → {e}")
            saltados += 1

    db_conn.close()

    # Update state
    if not list_candidates:
        estado["archivos"][filename] = {"mtime": mtime, "size": size}
        guardar_estado(estado)

    if list_candidates:
        print(f"  → {len(candidatos)} candidatos encontrados")
    else:
        print(f"  → {creados} creados, {saltados} saltados (ya existen/combo/sin precio/trend)")
    return creados


def main():
    parser = argparse.ArgumentParser(description="Auto-importador de WhatsApp")
    parser.add_argument("--watch", action="store_true", help="Modo watch: revisa cada N segundos")
    parser.add_argument("--interval", type=int, default=60, help="Intervalo en segundos (default: 60)")
    parser.add_argument("--margen", type=float, default=35, help="Margen de ganancia %% (default: 35)")
    parser.add_argument("--proveedor", default="GRUPO N23 MAYORISTA PM IMPORTADOS",
                        help="Nombre del proveedor (default: GRUPO N23...)")
    
    # Trend detection flags
    trend_group = parser.add_mutually_exclusive_group()
    trend_group.add_argument("--trend-only", action="store_true",
                             help="Importar solo productos que superen el umbral de tendencia")
    trend_group.add_argument("--list-candidates", action="store_true",
                             help="Listar candidatos con scores sin importar")
    parser.add_argument("--trend-threshold", type=int, default=TREND_THRESHOLD,
                        help=f"Umbral de tendencia 0-100 (default: {TREND_THRESHOLD})")
    
    args = parser.parse_args()

    estado = cargar_estado()
    
    # Pass config to procesar_archivo via function attributes
    if args.trend_only:
        procesar_archivo.trend_mode = 'trending-only'
    else:
        procesar_archivo.trend_mode = 'auto'
    procesar_archivo.trend_threshold = args.trend_threshold
    procesar_archivo.list_candidates = args.list_candidates

    def run_once():
        if not os.path.isdir(EXPORT_DIR):
            print(f"No existe {EXPORT_DIR}/")
            return

        txts = sorted([f for f in os.listdir(EXPORT_DIR) if f.endswith(".txt")])
        if not txts:
            print(f"No hay archivos .txt en {EXPORT_DIR}/")
            return

        total = 0
        for txt in txts:
            ruta = os.path.join(EXPORT_DIR, txt)
            try:
                total += procesar_archivo(ruta, args.proveedor, args.margen, estado)
            except Exception as e:
                print(f"  ✗ Error procesando {txt}: {e}")
        return total

    if args.watch:
        mode = "solo trending" if args.trend_only else "todos los productos"
        print(f"👁️  Watch mode cada {args.interval}s ({mode}, umbral: {args.trend_threshold})")
        print(f"   Ctrl+C para salir")
        try:
            while True:
                creados = run_once()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nDetenido.")
    else:
        run_once()


if __name__ == "__main__":
    main()
