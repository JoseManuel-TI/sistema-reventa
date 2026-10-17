"""Configuración común de tests.

Aísla la base de datos, imágenes, exports y config en un directorio temporal
ANTES de importar cualquier módulo de la app, para no tocar datos reales.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

_TMP = tempfile.mkdtemp(prefix="reventa_test_")

os.environ["APP_DATA_DIR"] = _TMP
os.environ["DATABASE_PATH"] = os.path.join(_TMP, "productos.db")
os.environ["IMAGES_DIR"] = os.path.join(_TMP, "imagenes")
os.environ["EXPORTS_DIR"] = os.path.join(_TMP, "exports")
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ.pop("DATABASE_URL", None)

import config  # noqa: E402

config.CONFIG_PATH = os.path.join(_TMP, "config.json")


@pytest.fixture(scope="session")
def app_module():
    import web
    web.app.config["TESTING"] = True
    return web


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


@pytest.fixture(autouse=True)
def _clean_db():
    """Deja la base vacía antes de cada test (salvo las tablas base)."""
    import db

    db.init_db()
    conn = db.get_connection()
    try:
        for tabla in ("pedido_items", "pedidos", "imagenes", "productos", "proveedores", "categorias"):
            conn.execute(db._sql(f"DELETE FROM {tabla}"))
        conn.commit()
    finally:
        conn.close()
    yield
