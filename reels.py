"""Generación de Reels 9:16 para Instagram a partir de la foto del producto.

Compone un frame 1080x1920 con el producto, precio y CTA usando Pillow y lo
convierte en un MP4 H.264 con el ffmpeg que trae `imageio-ffmpeg` (no requiere
instalar ffmpeg en el servidor).
"""

import hashlib
import os
import subprocess
import tempfile

import config
import db
import marketing

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

_FUENTES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FUENTES_REG = [
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


def _cover(img, ancho, alto):
    from PIL import Image

    ratio = max(ancho / img.width, alto / img.height)
    nueva = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
    img = img.resize(nueva, Image.LANCZOS)
    x = (img.width - ancho) // 2
    y = (img.height - alto) // 2
    return img.crop((x, y, x + ancho, y + alto))


def _fit(img, max_ancho, max_alto):
    from PIL import Image

    copia = img.copy()
    copia.thumbnail((max_ancho, max_alto), Image.LANCZOS)
    return copia


def _envolver(draw, texto, fuente, max_ancho, max_lineas=3):
    palabras = str(texto or "").split()
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if draw.textlength(prueba, font=fuente) <= max_ancho or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
            if len(lineas) == max_lineas:
                break
    if actual and len(lineas) < max_lineas:
        lineas.append(actual)
    if len(lineas) == max_lineas and palabras:
        ultima = lineas[-1]
        while ultima and draw.textlength(ultima + "…", font=fuente) > max_ancho:
            ultima = ultima[:-1]
        if ultima != lineas[-1]:
            lineas[-1] = ultima.rstrip() + "…"
    return lineas


def _pesos(valor):
    return "$ " + f"{float(valor or 0):,.0f}".replace(",", ".")


def componer_frame(producto, imagen_path, salida):
    """Dibuja el frame 1080x1920 del reel y lo guarda en `salida`."""
    from PIL import Image, ImageDraw, ImageFilter

    base = Image.open(imagen_path).convert("RGB")

    fondo = _cover(base, ANCHO, ALTO).filter(ImageFilter.GaussianBlur(28))
    fondo = Image.eval(fondo, lambda v: int(v * 0.42))
    lienzo = fondo.convert("RGBA")

    producto_img = _fit(base, 1000, 1000)
    px = (ANCHO - producto_img.width) // 2
    py = 250 + (1000 - producto_img.height) // 2
    lienzo.paste(producto_img, (px, py))

    draw = ImageDraw.Draw(lienzo)

    f_marca = _fuente(58, True)
    f_sub = _fuente(32, False)
    f_titulo = _fuente(60, True)
    f_precio = _fuente(100, True)
    f_cta = _fuente(46, True)
    f_pie = _fuente(30, False)

    def centrado(texto, y, fuente, color):
        ancho = draw.textlength(texto, font=fuente)
        draw.text(((ANCHO - ancho) / 2, y), texto, font=fuente, fill=color)

    centrado("ClickYa", 80, f_marca, (255, 255, 255))
    centrado(marketing.ENVIO_TEXTO, 160, f_sub, (209, 213, 219))

    y = 1310
    for linea in _envolver(draw, producto.get("nombre"), f_titulo, 960, 3):
        centrado(linea, y, f_titulo, (255, 255, 255))
        y += 72

    y += 10
    centrado(_pesos(producto.get("precio_venta")), y, f_precio, (52, 211, 153))
    y += 130

    texto_cta = "Pedilo en clickya.net"
    ancho_cta = draw.textlength(texto_cta, font=f_cta) + 100
    x0 = (ANCHO - ancho_cta) / 2
    draw.rounded_rectangle((x0, y, x0 + ancho_cta, y + 92), radius=46, fill=(16, 185, 129))
    cta_x = (ANCHO - draw.textlength(texto_cta, font=f_cta)) / 2
    draw.text((cta_x, y + 18), texto_cta, font=f_cta, fill=(255, 255, 255))

    centrado("Stock disponible · Link en bio", 1855, f_pie, (156, 163, 175))

    lienzo.convert("RGB").save(salida, "PNG", optimize=True)
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
        f"{producto['id']}|{producto.get('nombre')}|{producto.get('precio_venta')}".encode()
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
