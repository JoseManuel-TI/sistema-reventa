# Producción — ClickYa

> Estado y operación del entorno desplegado. Actualizado: **2026-10-18**.

## Infraestructura

- **Railway**: proyecto `mellow-determination`, servicio `web`, entorno `production`, región `sfo`.
- **URL de servicio**: `https://web-production-127a7c.up.railway.app` (respaldo/administración).
- **Backend**: Gunicorn (2 workers) sobre el `Procfile` (`python seed_railway.py; gunicorn web:app`).
- **Base**: SQLite en el volume persistente (sin `DATABASE_URL`). Seeder solo si el catálogo está vacío.

### Volume (crítico)

- Volume **`web-volume`** montado en **`/data`** sobre el servicio `web`.
- Ahí viven `productos.db`, `config.json`, `imagenes/`, `exports/` y el calendario de contenido.
- **Sin volume los datos se borran en cada deploy.** Fue la causa de la pérdida de productos/ pedidos. Ya está montado y verificado (los productos sobreviven a un redeploy).

## Dominio

- **`https://clickya.net`** (apex) y **`https://www.clickya.net`** (redirige 301 a la raíz).
- DNS en **Cloudflare** (nameservers `celine.ns.cloudflare.com`, `jake.ns.cloudflare.com`).
- Registros (proxy **DNS only**):
  - `CNAME @` → `7tn6iai1.up.railway.app`
  - `TXT _railway-verify` → `railway-verify=…`
  - `CNAME www` → `ok3pdtxa.up.railway.app`
  - `TXT _railway-verify.www` → `railway-verify=…`
- Ambos dominios agregados en Railway (`railway domain list`). Certificados válidos.
- La app usa `ProxyFix` (web.py) y un `before_request` que redirige `www.*` → raíz con 301.

## Variables de entorno (Railway → servicio `web`)

Gestión de tienda (tienen prioridad sobre `/configuracion`):

- `TIENDA_NOMBRE=ClickYa`, `TIENDA_WA=https://wa.me/5491126268359`, `TIENDA_COLOR=#2563eb`
- `DELIVERY_INFO`, `DOLAR_BLUE=1555.0`
- `BANCO=BBVA`, `BANCO_TITULAR`, `BANCO_CBU`, `BANCO_ALIAS`, `BANCO_TIPO`
- `META_PIXEL_ID=1834745577959538`, `GA_MEASUREMENT_ID=G-46K933MCRW`
- `TELEGRAM_CHAT_ID=8888470402`
- `PUBLIC_URL=https://clickya.net`

Secretos (no commitear):

- `ADMIN_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `SESSION_SECRET`

> Las env vars **pisan** lo que edites en `/configuracion`. Si querés gestionar una clave desde el panel, borrá su variable en Railway.

## Flujo de deploy

```sh
./.venv/bin/ruff check .          # lint
./.venv/bin/pytest                # tests (90)
git push origin main              # rama de deploy
railway redeploy --from-source -y # redeploy con el último commit
railway status                    # verificar Online
railway logs --deployment --lines 60
```

`main` es la rama desplegada. La rama `feat/amazon-afiliados` ya fue mergeada y quedó histórica.

## Operación

- **Admin**: `https://clickya.net/login` (solo contraseña: `ADMIN_PASSWORD`). Al entrar va a `/dashboard`.
- **Dashboard** (`/dashboard`): métricas, últimos productos (editar/eliminar) y pedidos recientes con **Cancelar** (devuelve stock).
- **Productos**: `/productos/nuevo` (o **+ Nuevo producto**).
- **Precios**: `/precios` incluye **“Recalcular todos”** (aplica el margen sobre costo al catálogo).
- **Pedidos**: `/pedidos`; estados `pendiente → confirmado → comprado → pagado → enviado → entregado` (y `cancelado`).

### Cargar productos desde WhatsApp

En `/productos/nuevo`, bloque **“📲 Importar desde WhatsApp”**: pegás el mensaje del grupo mayorista y *Autocompletar* extrae nombre, costo, beneficios y descripción. Después subís la foto. Parser en `importar_whatsapp.py` (interpreta precios en formato argentino).

### Modelo de precios

- **Margen sobre el costo (markup)**: `precio = costo × (1 + margen/100)`, por defecto **35%**.
- Costo en USD se convierte con el **dólar blue** (dolarapi.com, cache 1 h; fallback `DOLAR_BLUE`).
- Antes era “margen sobre precio de venta”; se cambió el 2026-10-18.

## Importante: local vs producción

El `localhost` y `clickya.net` tienen **bases separadas**. Cargar productos en local **no** los publica en la tienda. Cargá siempre en `https://clickya.net/login`. El localhost es solo para probar cambios.

## Historial reciente (rama `main`)

- `4359b95` — restaurar dashboard (productos, pedidos, cancelar con reposición de stock).
- `cf765ed` — margen sobre costo, importador de WhatsApp, recálculo masivo de precios.
- `6826e83` — `ProxyFix` para URLs `https://` detrás del proxy.
- `7d7d8ef` — `www.clickya.net` → 301 a la raíz.
- `7f20448` — seed idempotente (evita crash del deploy).
- `5997200` — nombre de tienda dinámico.

## Pendientes / próximos pasos

1. **Contenido / Instagram**: activar publicación automática (`/contenido`, `schedule_publicar.py` vía cron/scheduler).
2. **Carga de catálogo**: seguir cargando productos reales desde WhatsApp.
3. **Menor**: filtro de cancelados en `/pedidos`.
4. Backups del volume (`productos.db`, `config.json`, `imagenes/`).
