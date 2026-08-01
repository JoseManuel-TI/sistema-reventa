# Continuar — Amazon Afiliados (rama `feat/amazon-afiliados`)

> Para retomar el trabajo. Actualizado: 2026-08-01.

## Estado actual

Integración de productos afiliados de Amazon COMPLETA y probada en local. Commits pusheados a la rama:

- `e5331c7` — feat: productos afiliados de Amazon (es_afiliado/link_afiliado)
- `62e42fe` — fix: separar botón 'Ver precio en Amazon' del botón compartir
- `67c77ad` — feat: separar afiliados por categoría Amazon en la tienda

## Qué se hizo

1. **Modelo** (`db.py`): columnas `es_afiliado` (INTEGER/BOOLEAN, default 0) y `link_afiliado` (TEXT). Migración automática en `init_db()` (SQLite y Postgres).
2. **Tienda pública** (`tienda.py` + templates):
   - Catálogo, ficha y shortlink `/s/<id>` muestran afiliados sin `precio_venta`.
   - CTA "Ver precio en Amazon 🛒" con `target="_blank" rel="nofollow noopener"`.
   - Precio reemplazado por "Consultar precio en Amazon".
   - Filtro real por categoría `/tienda?cat=X` (tolera acentos/mayúsculas).
   - Barra de categorías dinámica (antes estática).
3. **Disclaimer Amazon** en footer de la tienda (`tienda/layout.html`).
4. **Admin** (`web.py` + `producto_form.html`): checkbox "Amazon / Afiliado" + link obligatorio (validación JS y server). Auto-categoriza como "Amazon" si no hay categoría.
5. **Extras**: badge "Amazon" en lista admin y ficha admin.

## Cómo probar

```sh
source .venv/bin/activate
python web.py   # → http://localhost:5000
```

- Admin: `test123` (ADMIN_PASSWORD en data/config.json).
- Flujo: Productos → + Nuevo → marcar "Amazon / Afiliado" → pegar link amzn.to/... → publicar.

## Pendiente / decidir

1. **Deploy**: rama `feat/amazon-afiliados` NO está en producción. Railway deploya solo la rama configurada (probablemente `main`).
   - Opción A: mergear a `main` (PR) → Railway → Deploy latest commit.
   - Opción B: cambiar rama en Railway Settings → Source → Branch.
2. **PA-API**: hoy solo links directos con tag. Si se quiere sincronizar precios/imágenes reales de Amazon, hay que integrar la Product Advertising API (requiere aprobación de Amazon Afiliados).
3. Los productos afiliados NO salen en exports (ML/Instagram) porque filtran `precio_venta > 0` — verificar si se quiere que aparezcan en Instagram.

## Ambiente

- **DB local**: `data/productos.db` (SQLite). Ya migrada con las columnas nuevas.
- **Nota**: `data/schedule.log` no está en git (excluido por .gitignore).
