# ClickYa — sistema de reventa

Tienda pública, administración de productos y pedidos, enlaces afiliados y herramientas de contenido. Python 3.12, Flask/Jinja2; SQLite local o PostgreSQL mediante `DATABASE_URL`.

## Iniciar en local

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_PASSWORD='elegí-una-contraseña-segura'
python web.py
```

Abrir `http://localhost:5000/tienda`. El panel está en `/productos`; los datos bancarios se editan en `/configuracion`. La base se inicializa automáticamente. Para comandos de consola: `python app.py --help`.

## Pedidos y transferencias

El único medio de pago de la tienda es la transferencia bancaria. Los afiliados se compran en su plataforma externa.

1. El comprador revisa el carrito y confirma sus datos. Se revalidan precio, disponibilidad y stock en una transacción.
2. Se crea un pedido **pendiente**, se reserva stock y se muestran banco, titular, CBU/alias y contacto por WhatsApp. Si faltan datos bancarios, se indica que el comercio los enviará para coordinar la transferencia.
3. El comercio verifica la acreditación en su cuenta y marca **pagado** en `/pedidos`. Un comprobante por sí solo no cambia el estado.
4. El comercio marca **enviado** y luego **entregado**.
5. Un pedido pendiente o pagado puede cancelarse: se devuelve su stock reservado una sola vez. Una transferencia ya recibida debe devolverse manualmente; el sistema no mueve dinero.

Los pedidos pendientes reservan stock hasta su cancelación manual. Revisarlos diariamente y contactar al comprador antes de cancelar. Los pedidos antiguos sin reserva no reponen stock al cancelarse; si se confirman como pagados, se comprueba y descuenta stock en ese momento.

El detalle público del pedido solo puede consultarse en el navegador que lo creó (hasta los últimos 20 pedidos de esa sesión) o desde una sesión de administrador. Para recuperar un pedido sin esa sesión, contactar al comercio. No se envía seguimiento automático por email.

## Persistencia y despliegue

- `APP_DATA_DIR`: directorio persistente de configuración, SQLite y calendario de publicaciones; por defecto `data/` o `/data` en Railway.
- `DATABASE_URL`: activa PostgreSQL. Sin ella se usa SQLite (`DATABASE_PATH` permite cambiar su ubicación).
- `SESSION_SECRET`: configurar un secreto estable en producción y compartirlo entre instancias. Sin esa variable se genera y guarda uno en `config.json`, compartido por los workers que usan el mismo volumen.
- `ADMIN_PASSWORD`: contraseña administrativa. Las variables de entorno tienen prioridad sobre la configuración guardada.
- `IMAGES_DIR` y `EXPORTS_DIR`: ubicaciones opcionales de imágenes y exportaciones.
- PostgreSQL no sustituye al volumen: configuración, imágenes y el calendario SQLite de contenido siguen necesitando almacenamiento persistente.
- En Railway se requieren HTTPS y volumen persistente. El `Procfile` ejecuta el seed y, solo si termina correctamente, Gunicorn con dos workers.
- El seed normal no modifica un catálogo existente. `--force` es una operación destructiva de reinicialización; no usar para actualizar producción.
- Hacer copia de seguridad de la base y del volumen antes de desplegar. Las migraciones añaden campos de reserva e idempotencia, sin borrar pedidos ni columnas históricas de pagos.

La publicación automática necesita programar `schedule_publicar.py` mediante cron o el scheduler del hosting. No se activa únicamente por arrancar la web. Ver `docs/AUTOMATIZACION_FASE_1.md`.

## Verificación

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Las pruebas usan datos temporales y simulan notificaciones; no escriben pedidos en la base real ni publican mensajes. Cubren transferencias, privacidad, CSRF, cambios de precio, stock concurrente, doble envío, estados y páginas principales. La suite local utiliza SQLite; el despliegue PostgreSQL requiere una comprobación de integración en su entorno.
