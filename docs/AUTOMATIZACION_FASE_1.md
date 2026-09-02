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

## Configuración necesaria para alertas

En `/configuracion` o variables de entorno:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Sin esos valores, la compra no falla, pero no se envía el aviso.

## Cron sugerido

```cron
0 10 * * * cd /ruta/proyecto && /usr/bin/python3 schedule_publicar.py >> data/schedule.log 2>&1
```
