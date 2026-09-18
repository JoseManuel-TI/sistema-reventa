"""Persistent config — stores store settings & bank transfer info in data/config.json"""

import os, json
import fcntl
import tempfile
import secrets
from contextlib import contextmanager

DATA_DIR = os.environ.get("APP_DATA_DIR") or (
    "/data" if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_NAME")
    else os.path.join(os.path.dirname(__file__), "data")
)
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULTS = {
    "BANCO": "",
    "BANCO_TITULAR": "",
    "BANCO_CBU": "",
    "BANCO_ALIAS": "",
    "BANCO_TIPO": "Caja de Ahorro",
    "TIENDA_NOMBRE": "Mi Tienda",
    "TIENDA_LOGO": "",
    "TIENDA_COLOR": "#2563eb",
    "TIENDA_DESCRIPCION": "",
    "TIENDA_WA": "#",
    "SESSION_SECRET": "",
    "ADMIN_PASSWORD": "",
    "DOLAR_BLUE": "1510",
    "DELIVERY_INFO": "Se entrega dentro de las 24 hs hábiles posteriores a la confirmación del pago.",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "FB_PAGE_TOKEN": "",
    "FB_PAGE_ID": "",
    "IG_BUSINESS_ID": "",
    "PUBLIC_URL": "https://clickya.net",
}

def _load():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

@contextmanager
def _config_lock():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _save(data):
    fd, path = tempfile.mkstemp(dir=DATA_DIR, prefix=".config-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(path, CONFIG_PATH)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def session_secret():
    with _config_lock():
        value = os.environ.get("SESSION_SECRET") or _load().get("SESSION_SECRET")
        if not value:
            value = secrets.token_hex(32)
            cfg = _load()
            cfg["SESSION_SECRET"] = value
            _save(cfg)
        return value


def get(key):
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    cfg = _load()
    if key in cfg:
        return cfg[key]
    return DEFAULTS.get(key, "")

def set(key, value):
    with _config_lock():
        cfg = _load()
        cfg[key] = value
        _save(cfg)
    return value

def get_all():
    cfg = _load()
    result = {}
    for k in DEFAULTS:
        env_val = os.environ.get(k)
        if env_val is not None:
            result[k] = env_val
        elif k in cfg:
            result[k] = cfg[k]
        else:
            result[k] = DEFAULTS[k]
    return result

def set_many(data):
    with _config_lock():
        cfg = _load()
        cfg.update(data)
        _save(cfg)

def datos_bancarios_completos():
    return bool(get("BANCO_CBU") or get("BANCO_ALIAS"))
