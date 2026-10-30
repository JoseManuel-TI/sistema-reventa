"""Generación de Reels 9:16 para Instagram a partir de la foto del producto.

Compone un frame 1080x1920 con el producto, precio y CTA usando Pillow y lo
convierte en un MP4 H.264 con el ffmpeg que trae `imageio-ffmpeg` (no requiere
instalar ffmpeg en el servidor).
"""

import hashlib
import os
import re
import subprocess
import tempfile

import config
import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = config.DATA_DIR
IMAGENES_DIR = os.environ.get("IMAGES_DIR") or (
    os.path.join(DATA_DIR, "imagenes")
    if os.environ.get("RAILWAY_ENVIRONMENT")
    else os.path.join(BASE_DIR, "imagenes")
)
REELS_DIR = os.path.join(IMAGENES_DIR, "reels")

ANCHO, ALTO = 1080, 1920
DURACION = 8
_VERSION_FRAME = "4"

_NO_DIBUJABLES = re.compile(r"[^\x20-\x7E\xA0-\xFF\u2010-\u203A\u20AC\u00A3\u00A5\u20BF]+")


def _limpiar_texto(texto):
    """Quita emojis/símbolos que la tipografía del video no puede dibujar (tofu)."""
    limpio = _NO_DIBUJABLES.sub(" ", str(texto or ""))
    return " ".join(limpio.split())

_FUENTES_BOLD = [
    os.path.join(BASE_DIR, "fonts", "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FUENTES_REG = [
    os.path.join(BASE_DIR, "fonts", "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def _ffmpeg():
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def disponible():
    """True si se puede generar el video (Pillow + ffmpeg embebido)."""
    if str(config.get("IG_REELS") or "1").strip().lower() in ("0", "no", "false", "off"):
        return False
    try:
        import imageio_ffmpeg  # noqa: F401
        import PIL  # noqa: F401
    except Exception:
        return False
    return True


def _fuente(tamano, bold=True):
    from PIL import ImageFont

    for ruta in _FUENTES_BOLD if bold else _FUENTES_REG:
        if os.path.exists(ruta):
            try:
                return ImageFont.truetype(ruta, tamano)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=tamano)
    except Exception:
        return ImageFont.load_default()


def _fuente_archivo(archivo):
    """Resuelve la ruta local de una imagen del producto."""
    if archivo.startswith("imagenes/"):
        return os.path.join(IMAGENES_DIR, archivo[len("imagenes/"):])
    if os.path.isabs(archivo):
        return archivo
    return os.path.join(BASE_DIR, archivo)


def _fit(img, max_ancho, max_alto):
    from PIL import Image

    copia = img.copy()
    copia.thumbnail((max_ancho, max_alto), Image.LANCZOS)
    return copia


def _envolver(draw, texto, fuente, max_ancho, max_lineas=3):
    palabras = str(texto or "").split()
    lineas, actual, truncado = [], "", False
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if draw.textlength(prueba, font=fuente) <= max_ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
            if len(lineas) == max_lineas:
                truncado = True
                break
    if actual and len(lineas) < max_lineas:
        lineas.append(actual)
    if truncado:
        ultima = lineas[-1]
        while ultima and draw.textlength(ultima + "…", font=fuente) > max_ancho:
            ultima = ultima[:-1]
        lineas[-1] = ultima.rstrip() + "…"
    return lineas


def componer_frame(producto, imagen_path, salida):
    """Dibuja una plantilla de marca uniforme en 1080x1920."""
    from PIL import Image, ImageDraw

    base = Image.open(imagen_path).convert("RGB")
    lienzo = Image.new("RGB", (ANCHO, ALTO), (15, 23, 42))
    draw = ImageDraw.Draw(lienzo)
    azul, amarillo, blanco = (37, 99, 235), (245, 158, 11), (255, 255, 255)
    draw.rectangle((0, 0, ANCHO, 18), fill=azul)

    f_marca = _fuente(78, True)
    f_sub = _fuente(38, False)
    f_titulo = _fuente(66, True)
    f_precio = _fuente(48, True)
    f_cta = _fuente(53, True)
    f_pie = _fuente(32, False)

    def centrado(texto, y, fuente, color):
        ancho = draw.textlength(texto, font=fuente)
        draw.text(((ANCHO - ancho) / 2, y), texto, font=fuente, fill=color)

    centrado("ClickYa", 64, f_marca, blanco)
    centrado("Tecnología · Hogar · Perfumes", 160, f_sub, (203, 213, 225))

    draw.rounded_rectangle((68, 268, 1012, 1110), radius=48, fill=blanco)
    producto_img = _fit(base, 880, 780)
    px = (ANCHO - producto_img.width) // 2
    py = 298 + (780 - producto_img.height) // 2
    lienzo.paste(producto_img, (px, py))

    titulo = _limpiar_texto(producto.get("nombre"))
    for i, linea in enumerate(_envolver(draw, titulo, f_titulo, 940, 2)):
        centrado(linea, 1170 + i * 82, f_titulo, blanco)

    centrado("Precio actualizado en la tienda", 1410, f_precio, amarillo)
    draw.rounded_rectangle((90, 1545, 990, 1670), radius=60, fill=azul)
    centrado("Comprá en clickya.net", 1574, f_cta, blanco)
    centrado("Envíos en AMBA · Consultá disponibilidad", 1824, f_pie, (203, 213, 225))

    lienzo.save(salida, "PNG", optimize=True)
    return salida


def generar_reel(producto, base_url="https://clickya.net"):
    """Genera (o reutiliza) el reel del producto.

    Retorna (ok, url_publica_o_error).
    """
    if not disponible():
        return False, "Generación de Reels no disponible"

    imgs = db.get_imagenes(producto["id"])
    if not imgs:
        return False, "Producto sin imagen"
    origen = _fuente_archivo(imgs[0]["archivo"])
    if not os.path.exists(origen):
        return False, f"Imagen no encontrada: {os.path.basename(origen)}"

    clave = hashlib.sha1(
        f"{_VERSION_FRAME}|{producto['id']}|{producto.get('nombre')}|{producto.get('precio_venta')}".encode()
    ).hexdigest()[:10]
    os.makedirs(REELS_DIR, exist_ok=True)
    nombre = f"{producto['id']}_{clave}.mp4"
    destino = os.path.join(REELS_DIR, nombre)

    if not (os.path.exists(destino) and os.path.getmtime(destino) >= os.path.getmtime(origen)):
        with tempfile.TemporaryDirectory(dir=DATA_DIR) as tmp:
            frame = os.path.join(tmp, "frame.png")
            componer_frame(producto, origen, frame)
            cmd = [
                _ffmpeg(), "-y",
                "-i", frame,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(DURACION),
                "-vf",
                f"zoompan=z='min(zoom+0.0007,1.10)':d={DURACION * 25}"
                f":s={ANCHO}x{ALTO}:fps=25,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest",
                "-movflags", "+faststart",
                destino,
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=180)
            except subprocess.TimeoutExpired:
                return False, "Timeout generando el video"
            if proc.returncode != 0 or not os.path.exists(destino):
                error = (proc.stderr or b"").decode(errors="replace")[-300:]
                return False, f"ffmpeg falló: {error}"

    url = f"{base_url.rstrip('/')}/imagenes/reels/{nombre}"
    return True, url
