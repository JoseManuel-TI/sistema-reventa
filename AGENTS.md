# AGENTS.md

App Flask (monolito) para gestión y venta online de reventa (ClickYa).

## Entorno

- Requiere Python 3.12 (ver `runtime.txt`).
- Crear/entrar al venv:

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
```

## Comandos

- Lint: `./.venv/bin/ruff check .` (auto-fix: `./.venv/bin/ruff check --fix .`)
- Tests: `./.venv/bin/pytest`
- Servidor local: `./.venv/bin/python web.py` (http://localhost:5000)
- Compilar todo: `./.venv/bin/python -m compileall -q *.py scripts/*.py tests/*.py`

## Convenciones

- Config de lint/tests en `pyproject.toml`. No agregar `pytest.ini`/`ruff.toml`.
- Tests aislados en `tests/`: `conftest.py` fija `APP_DATA_DIR`/`IMAGES_DIR`/`EXPORTS_DIR`/
  `SESSION_SECRET`/`ADMIN_PASSWORD` en un temp dir ANTES de importar `web`/`db`.
  Nunca tocar `data/` real desde tests.
- Backend DB dual: SQLite (local) y Postgres vía `DATABASE_URL`; todo SQL pasa por
  `db._sql()` (placeholders `?` → `%s`).
- Pedidos: `db.crear_pedido()` revalida stock/precio y recalcula el total en el servidor.
- CSRF: todo POST lleva `csrf_token` (o header `X-CSRF-Token`); no desactivar
  `_proteger_csrf`. Desde JS usar `document.querySelector` del campo oculto.
- Secretos vía env (`SESSION_SECRET`, `ADMIN_PASSWORD`, etc.), nunca hardcodear.

## CI

`.github/workflows/ci.yml` corre `ruff check .` y `pytest` en Python 3.12.
