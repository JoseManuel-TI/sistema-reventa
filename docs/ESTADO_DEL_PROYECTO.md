# Estado del proyecto — 2026-10-18

La descripción operativa está en [README.md](../README.md) y el detalle del entorno
desplegado en [PRODUCCION.md](PRODUCCION.md).

## En producción (`https://clickya.net`)

- Tienda pública, administración con contraseña y CSRF, carrito, pedidos por transferencia
  bancaria y **contra entrega**, reserva transaccional de stock, cancelación con reposición.
- **Dashboard** (`/dashboard`): métricas, últimos productos con editar/eliminar y pedidos
  recientes con cancelación (devuelve stock). Al iniciar sesión se entra acá.
- **Precios con margen sobre el costo** (markup, 35% por defecto); costo en USD se convierte
  con el **dólar blue**. Botón “Recalcular todos” en `/precios`.
- **Importador de WhatsApp**: en `/productos/nuevo` se pega el mensaje del grupo y se
  autocompletan nombre, costo, beneficios y descripción (`importar_whatsapp.py`).
- Afiliados de Amazon con seguimiento de clics, exportaciones y contenido programable.
- Dominio propio `clickya.net` (+ `www` con 301), HTTPS y **volume persistente** en `/data`.

## Notas

- El checkout **no** usa Mercado Pago; la acreditación bancaria se comprueba y se marca
  manualmente.
- **El volumen es obligatorio**: sin él la base se reinicia en cada deploy (incidente
  resuelto el 2026-10-18 montando `web-volume` en `/data`).
- `localhost` y producción tienen **bases separadas**: cargar productos en producción.
- PostgreSQL (`DATABASE_URL`) es opcional y no reemplaza al volumen.

## Verificación

`ruff check .` limpio y `pytest` (90 tests) en verde. El seed no sobrescribe un catálogo
existente.
