# Sistema Reventa — Estado del Proyecto

## Datos clave

| Campo | Valor |
|---|---|
| **Nombre** | ClickYa |
| **Eslogan** | Todo · Rápido · Fácil |
| **URL producción** | https://clickya.net/tienda |
| **Admin** | https://clickya.net/dashboard |
| **Repositorio** | https://github.com/JoseManuel-TI/sistema-reventa.git |
| **Hosting** | ClickYa.net (Railway-like) |
| **Stack** | Python 3.12 + Flask + SQLite3 + Jinja2 |
| **Deploy** | GitHub → ClickYa.net (automático) |

## Estructura del proyecto

```
sistema-reventa/
├── web.py                  # Flask server (admin panel + rutas)
├── tienda.py               # Blueprint tienda pública (catálogo, carrito, checkout)
├── db.py                   # Capa de datos SQLite3
├── config.py               # Config persistente (data/config.json)
├── precios.py              # Calculadora de precios (ARS y USD)
├── importar_whatsapp.py    # Importación desde WhatsApp
├── exportar.py             # Exportación a ML, HTML, Instagram, JSON
├── app.py                  # CLI (argparse) para gestión offline
├── seed_railway.py         # Seed automático en Railway (usa seed.json)
├── Procfile                # gunicorn web:app
├── runtime.txt             # python-3.12
├── requirements.txt        # flask, gunicorn
├── .gitignore              # ignora .db, config.json, exports/, etc.
│
├── data/
│   ├── productos.db        # Base de datos SQLite
│   ├── config.json         # Config (banco, dolar_blue, etc.)
│   ├── seed.json           # Datos semilla
│   └── whatsapp_export/    # Archivos .txt e imágenes de WhatsApp
│
├── templates/              # Jinja2 templates (admin)
│   ├── layout.html
│   ├── producto_form.html  ← Formulario crear/editar producto (YA TIENE costo_usd)
│   ├── producto_detail.html
│   ├── productos.html
│   ├── configuracion.html
│   ├── precios.html
│   ├── tienda/             # Templates tienda pública
│   │   ├── catalogo.html
│   │   ├── producto.html
│   │   ├── carrito.html
│   │   ├── checkout.html
│   │   └── gracias.html
│   └── ... (resto)
│
├── static/
│   ├── style.css
│   └── tienda.css
│
├── imagenes/proveedores/   # Imágenes organizadas por proveedor
├── scripts/
│   ├── autoimport.py       # Auto-importador watch mode
│   └── trending.py         # Motor de scoring de tendencias
├── docs/
│   ├── SALIR_AL_MERCADO.md # Plan de salida a producción
│   └── ESTADO_DEL_PROYECTO.md  ← Este archivo
└── exports/                # Exportaciones generadas
```

## Base de datos (SQLite)

### Tabla `productos`
```sql
id, nombre, descripcion, proveedor_id, costo (ARS), precio_venta (ARS),
margen_porcentaje, iva_porcentaje, categoria, stock, activo, publicar,
costo_usd (USD), created_at, updated_at
```

### Otras tablas
`proveedores`, `imagenes`, `pedidos`, `pedido_items`

## Estado de cambios locales (sin commit)

Hay **2 archivos modificados** sin commit:

1. **`templates/producto_form.html`** — Se agregó campo `costo_usd` (Costo USD) en el formulario de producto
2. **`web.py`** — Se agregó lectura de `costo_usd` en rutas `productos_nuevo` y `productos_editar`

Estos cambios están SOLO en local. **No están en producción.** Para que estén en producción hay que:
```
git add -A && git commit -m "feat: add costo_usd field to product form and routes"
git push origin main
```
ClickYa.net hace deploy automático al recibir push.

## Historial de commits

```
eab99ba fix: match images by media sequence order, skip combos from photo index
b9d2c9f feat: import 23 products from WhatsApp, seed script for Railway
f062c93 fix: dolar blue 1510 (valor real)
198ea02 feat: precios en USD + dolar blue + dedup + evitar combos
2cda7ec feat: autenticacion con login para admin
65e018c fix: raiz redirige a tienda, admin en /dashboard
c3101ed fix: agregar columna publicar a productos + migracion
1b02a42 feat: preparar para Railway (gunicorn, Procfile, PORT env)
8dac784 Initial commit
```

## Precios y USD

### Cómo funciona
1. `config.py` — `DOLAR_BLUE` default 1510, configurable desde `/configuracion`
2. `precios.py` — `calcular_precio_desde_usd(costo_usd, margen)` convierte USD → ARS
3. Importación WhatsApp: si detecta precio USD, lo guarda en `costo_usd` y calcula precio_venta automáticamente
4. **NUEVO**: ahora se puede editar `costo_usd` manualmente desde el formulario de producto

### Problemas conocidos
- [x] ~~No había campo `costo_usd` en el formulario~~ → YA RESUELTO (local, falta commit+push)
- [ ] El `costo_usd` no recalcula automáticamente el `precio_venta` al editarlo manualmente (hay que hacerlo desde la calculadora de precios)
- [ ] `costo_usd` no se muestra como columna en la lista de productos (solo en detalle)

## Hosting: ClickYa.net

ClickYa.net es la plataforma donde está hosteada la app. Se desconoce el mecanismo exacto de deploy y reinicio. Probables opciones:
- Conectado a GitHub (push → auto-deploy)
- Panel web con botón "Deploy" / "Restart"
- FTP / SCP

Para acceder al panel admin: https://clickya.net/dashboard (requiere contraseña).

## Próximos pasos documentados en SALIR_AL_MERCADO.md

- [ ] Contratar VPS (Hostinger / DigitalOcean)
- [ ] Comprar dominio clickya.com.ar
- [ ] Configurar HTTPS
- [ ] Deploy manual o migrar a VPS
- [ ] Publicar contenido en Instagram (@clickya.ar)
- [ ] Configurar WhatsApp Business
- [ ] Marcar productos como publicados
