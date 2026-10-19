"""Dispara el respaldo diario de ClickYa.

Pensado para un cron (p. ej. servicio Railway Cron `backup-cron`). Hace una
petición autenticada con `CRON_TOKEN` al endpoint `/backup/cron` del sitio, que
crea el ZIP del volume y lo manda a Telegram.

Variables:
    CRON_TOKEN  secreto compartido con la web (obligatorio).
    PUBLIC_URL  base del sitio (por defecto `https://clickya.net`).

Uso:
    python cron_backup.py
"""

import os
import sys
import urllib.error
import urllib.request


def main():
    base = (os.environ.get("PUBLIC_URL") or "https://clickya.net").rstrip("/")
    token = os.environ.get("CRON_TOKEN")
    if not token:
        print("CRON_TOKEN no configurado.", file=sys.stderr)
        return 1

    req = urllib.request.Request(
        f"{base}/backup/cron",
        data=b"",
        method="POST",
        headers={"X-Cron-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            print(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:300]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Error de conexión: {e.reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
