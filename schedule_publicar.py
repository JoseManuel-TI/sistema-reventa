"""
Script para cron/launchd — publica contenido pendiente en Telegram.
Uso:
    python3 schedule_publicar.py           # publica pendientes
    python3 schedule_publicar.py --setup    # programa todos si no hay nada

Para crontab (una vez al día):
    0 10 * * * cd /ruta/proyecto && /usr/bin/python3 schedule_publicar.py >> data/schedule.log 2>&1
"""

import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import contenido
try:
    import instagram_api
except ImportError:
    instagram_api = None

if __name__ == "__main__":
    import config as cfg
    base_url = cfg.get("PUBLIC_URL") or "https://clickya.net"

    if instagram_api:
        ok, msg = instagram_api.verificar_conexion()
        print(f"📸 Instagram: {msg}")

    if "--setup" in sys.argv:
        count = contenido.programar_todos()
        print(f"Programadas {count} publicaciones.")
    else:
        result = contenido.publicar_pendientes(base_url=base_url)
        for pid, ok, msg in result:
            status = "✅" if ok else "❌"
            print(f"{status} Prod#{pid}: {msg}")
        if not result:
            print("Sin publicaciones pendientes.")
            count = contenido.programar_todos()
            if count:
                print(f"Programadas {count} nuevas publicaciones.")
