# ClickYa — Automatización Fase 1

## Qué quedó automatizado

- Rutina diaria de contenido.
- Programación automática de productos locales con stock, precio e imagen.
- Priorización de productos gancho para venta directa.
- Publicación de pendientes por Telegram y, si está configurado, Instagram.
- Resumen operativo por Telegram.
- Alerta inmediata por Telegram cuando entra un pedido nuevo desde checkout.

## Comandos

```sh
python3 app.py publicar --diario
```

Ejecuta la rutina completa:

1. Completa la cola de publicaciones para los próximos 7 días.
2. Publica solo 1 publicación programada para el día actual.
3. Genera diagnóstico comercial.
4. Envía resumen a Telegram si hay token configurado.

Las publicaciones atrasadas no se publican en bloque desde la rutina diaria para evitar spam si quedó backlog.

```sh
python3 schedule_publicar.py
```

Hace lo mismo, pensado para cron o launchd.

```sh
python3 schedule_publicar.py --solo-publicar
```

Solo publica pendientes, sin rellenar calendario.
Este modo sí procesa publicaciones atrasadas.

```sh
python3 app.py publicar --calendario
```

Muestra la cola y resume totales, pendientes, publicados, errores y atrasadas.

```sh
python3 app.py publicar --reprogramar-atrasadas
```

Mueve publicaciones pendientes vencidas a fechas futuras libres, una por día.

```sh
python3 app.py publicar --cancelar-atrasadas
```

Cancela publicaciones pendientes vencidas para limpiar backlog obsoleto.

## Panel admin

Entrar a `/contenido` y usar el botón **Rutina diaria**.
La pantalla también muestra diagnóstico comercial y permite reprogramar o cancelar publicaciones atrasadas.

## Afiliados Amazon

La tienda usa tracking interno para enlaces afiliados:

- El cliente ve botones como **Ver en Amazon**.
- El clic pasa primero por `/out/<producto_id>?src=...`.
- El sistema registra producto, plataforma, origen del clic, referer, user-agent e IP anonimizada.
- Luego redirige al link real de Amazon.

Métricas:

- `/contenido/afiliados` muestra clicks totales, clicks de hoy, últimos 7 días y ranking por producto.
- La landing recomendada para campañas es `/tienda?origen=amazon`.

Flujo manual recomendado:

1. Publicar en Instagram/Facebook una recomendación concreta.
2. Enviar tráfico a `https://clickya.net/tienda?origen=amazon` o al producto puntual.
3. Revisar `/contenido/afiliados` para identificar qué productos reciben clicks.
4. Repetir publicaciones de los productos con mejor CTR y reemplazar los que no reciben interés.

## Configuración necesaria para alertas

En `/configuracion` o variables de entorno:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Sin esos valores, la compra no falla, pero no se envía el aviso.

## Scheduler en producción (Railway)

La web expone `POST/GET /contenido/cron`, que ejecuta `contenido.rutina_diaria()`. Se autentica
con el secreto `CRON_TOKEN` (header `X-Cron-Token` o query `?token=`); sin él responde **403**.

- Servicio Railway **`contenido-cron`** (mismo repo `sistema-reventa`, rama `main`).
- `cronSchedule`: `0 13 * * *` — **UTC**, equivale a **10:00 ART**. Railway corre el cron en UTC.
- `startCommand`: `python cron_contenido.py` (cliente `cron_contenido.py` llama al endpoint con el token).
- Variables: `CRON_TOKEN` vive en el servicio `web`; en `contenido-cron` es `${{web.CRON_TOKEN}}`.
- Prueba manual:

```sh
curl -s -X POST -H "X-Cron-Token: $CRON_TOKEN" https://clickya.net/contenido/cron
# {"ok": true, "programadas": 7, "publicadas": 1, "pendientes": 6, "telegram": true, ...}
```

Nota: si la rutina se ejecuta más de una vez en el mismo día vuelve a publicar el cupo de hoy
(la fecha queda libre al publicarse). En operación normal corre **una vez por día**.

## Instagram (auto-publicación)

`instagram_api.py` publica a Instagram si están configuradas las variables
`FB_PAGE_TOKEN`, `FB_PAGE_ID` e `IG_BUSINESS_ID`. Requiere cuenta IG **Business/Creator**
vinculada a una página de Facebook y una app en Meta for Developers con permisos de
publicación. Mientras no estén, la rutina solo publica en Telegram.

## Cron local (alternativa sin Railway)

```cron
0 10 * * * cd /ruta/proyecto && /usr/bin/python3 schedule_publicar.py >> data/schedule.log 2>&1
```
