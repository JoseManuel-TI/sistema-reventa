"""Respaldo del volume de ClickYa (base, config e imágenes).

Arma un ZIP con una copia consistente de la base SQLite (API de backup),
`contenido.db`, `config.json` y la carpeta de imágenes. Se usa desde el endpoint
`/backup/cron` (protegido con `CRON_TOKEN`), que manda el ZIP a Telegram, y
también se puede correr a mano:

    python backup.py

Variables: las mismas del resto de la app (`APP_DATA_DIR`, `DATABASE_PATH`,
`IMAGES_DIR`).
"""

import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime

import config

TELEGRAM_MAX_BYTES = 45 * 1024 * 1024


def _data_dir():
    return config.DATA_DIR


def _imagenes_dir():
    return os.environ.get("IMAGES_DIR") or os.path.join(_data_dir(), "imagenes")


def _copiar_sqlite(origen, destino):
    """Copia consistente de una base SQLite (aunque esté en uso)."""
    con_o = sqlite3.connect(origen)
    try:
        con_d = sqlite3.connect(destino)
        try:
            con_o.backup(con_d)
        finally:
            con_d.close()
    finally:
        con_o.close()


def crear_backup(destino=None, incluir_imagenes=True):
    """Crea el ZIP y devuelve {"path", "nombre", "bytes", "incluye_imagenes"}."""
    data_dir = _data_dir()
    if destino is None:
        destino = tempfile.mkdtemp(prefix="backup_clickya_")
    os.makedirs(destino, exist_ok=True)

    nombre = f"clickya_backup_{datetime.now():%Y%m%d_%H%M%S}.zip"
    path = os.path.join(destino, nombre)

    db_path = os.environ.get("DATABASE_PATH") or os.path.join(data_dir, "productos.db")
    tmp_db = os.path.join(destino, "_productos.db")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(db_path):
            _copiar_sqlite(db_path, tmp_db)
            z.write(tmp_db, "productos.db")
            os.unlink(tmp_db)
        else:
            z.writestr("FALTA_productos.db.txt", "No se encontró la base de productos.")

        for extra in ("contenido.db", "config.json"):
            ruta = os.path.join(data_dir, extra)
            if os.path.exists(ruta):
                z.write(ruta, extra)

        if incluir_imagenes:
            base_img = _imagenes_dir()
            for raiz, _dirs, archivos in os.walk(base_img):
                for archivo in archivos:
                    completo = os.path.join(raiz, archivo)
                    rel = os.path.relpath(completo, base_img)
                    z.write(completo, os.path.join("imagenes", rel))

        z.writestr(
            "LEEME.txt",
            "Respaldo ClickYa\n"
            f"Generado: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"Incluye imágenes: {'sí' if incluir_imagenes else 'no'}\n",
        )

    return {
        "path": path,
        "nombre": nombre,
        "bytes": os.path.getsize(path),
        "incluye_imagenes": incluir_imagenes,
    }


def ejecutar(destino=None):
    """Crea el respaldo; si supera el límite de Telegram, reintenta sin imágenes."""
    info = crear_backup(destino=destino, incluir_imagenes=True)
    if info["bytes"] > TELEGRAM_MAX_BYTES:
        os.unlink(info["path"])
        info = crear_backup(destino=destino, incluir_imagenes=False)
        info["motivo_sin_imagenes"] = "El ZIP con imágenes superaba el límite de Telegram."
    return info


if __name__ == "__main__":
    resultado = ejecutar()
    mb = resultado["bytes"] / (1024 * 1024)
    print(f"Respaldo: {resultado['path']} ({mb:.2f} MB, imágenes={resultado['incluye_imagenes']})")
