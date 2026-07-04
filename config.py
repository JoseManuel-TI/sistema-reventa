"""Persistent config — stores store settings & bank transfer info in data/config.json"""

import os, json

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "config.json")

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
    "DELIVERY_INFO": "Se entrega dentro de las 24 hs hábiles posteriores a la confirmación del pago.",
}

def _load():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

def _save(data):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)

def get(key):
    return os.environ.get(key) or _load().get(key) or DEFAULTS.get(key, "")

def get_all():
    cfg = _load()
    return {k: os.environ.get(k) or cfg.get(k, DEFAULTS[k]) for k in DEFAULTS}

def set_many(data):
    cfg = _load()
    cfg.update(data)
    _save(cfg)

def datos_bancarios_completos():
    return bool(get("BANCO_CBU") or get("BANCO_ALIAS"))
