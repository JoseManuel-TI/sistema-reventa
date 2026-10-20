# Plan de monetización con afiliados (Amazon + Hotmart)

Fecha: 2026-10-20 · Estado: propuesta para aprobar

## 1. Diagnóstico

Lo que ya existe en producción:

| Pieza | Estado actual |
|---|---|
| Verticales en la tienda | `Productos` (stock local), `Amazon Importados`, `Cursos Digitales` (filtro `?origen=`) |
| Productos Amazon | 5 publicados, sin precio, con CTA externo |
| Productos Hotmart | 0 cargados (el formulario ya soporta la plataforma) |
| Clicks afiliados | 41 en 7 días (SSD T7: 11, Tapo C210: 8, Kindle: 8, DJI Mic: 8, Echo Dot: 6) |
| Tracking | Tabla `clicks_afiliados` (producto, plataforma, origen, referer, UA, IP hash) |
| Divulgación | Aviso de afiliado Amazon en el footer + franja en el catálogo Amazon |
| Enlaces salientes | Redirección propia `/out/<id>?src=...` |
| Carrito | Solo stock local. Los afiliados van directo a la plataforma |

Brechas principales:

1. **Riesgo Amazon**: la redirección propia puede leerse como *cloaking*. Amazon prohíbe ocultar que el destino es Amazon (incluye “Redirecting Links”).
2. **Sin atribución**: el link final no lleva `ascsubtag` (Amazon) ni `src` (Hotmart); no se puede saber qué ubicación convierte.
3. **Divulgación incompleta**: falta aviso al lado del CTA y en los captions de Telegram/IG (`#Publicidad`, “enlace de afiliado”).
4. **Claims incorrectos**: las cards externas muestran “Envío a Argentina” también para cursos Hotmart; los captions de IG asumen precio/stock local.
5. **Hotmart desaprovechado**: es el canal con mejor margen para Argentina y no hay productos.
6. **Tienda mezclada**: el home/catálogo muestra todo junto; las verticales existen pero no tienen landing propia ni jerarquía visual.
7. **Sin selecciones**: no se pueden agrupar varios productos en una página (“Top 3”, “setup gamer”).
8. **Sin seguimiento de comisiones**: solo clicks; no hay ingresos reales ni EPC.

## 2. Recomendación ejecutiva

1. **Un solo dominio, tres verticales.** No separar en varios sitios: se pierde autoridad SEO, se duplica mantenimiento y se fragmenta el tráfico de Instagram.
2. **Hotmart como motor de ingresos** (comisión 30–70 %, entrega digital, pago con Mercado Pago en Argentina). **Amazon como catálogo/descubrimiento** (comisión baja, envío internacional y aduana desincentivan la compra).
3. **Cumplimiento primero**: enlaces directos, divulgación visible y claims correctos. Un cierre de cuenta de Amazon cuesta más que cualquier optimización.
4. **“Selecciones” en lugar de carrito unificado.** No existe forma legítima de meter Amazon + Hotmart en un mismo checkout. Sí se pueden agrupar varios productos en una página curada y que cada uno abra su plataforma.
5. **Medir antes de escalar**: clicks por ubicación → selecciones → comisiones reales (carga mensual de reportes).

## 3. Cumplimiento (hacer antes de crecer)

### Amazon Associates

- **Enlaces directos** a Amazon con el tag, sin redirección propia. Si se mantiene `/out`, que sea solo para plataformas que no lo prohíben.
- Agregar **`ascsubtag`** por ubicación (`clickya_web_card_42`, `clickya_tg_42`) para atribución en el reporte de Amazon.
- **Divulgación** en el sitio y a nivel de enlace: “Enlace de afiliado: ClickYa puede recibir una comisión sin costo extra para vos”.
- **No mostrar precios** de Amazon (hoy se cumple: “Precio disponible en Amazon”).
- **No usar links en email ni en material offline**. En WhatsApp masivo, evitar el link directo: mandar a la web/bio.
- No autocompras, no incentivos por click, no pedir bookmark ni “clickeá mi link”.
- Ventana de atribución: **89 días**; pago ~60 días después del cierre de mes; mínimo USD 10 (gift card) / USD 100 (cheque).
- **Cobro desde Argentina**: W-8BEN + cuenta en USD (Payoneer/Wise como *receiving account*). Argentina no tiene tratado fiscal con EE. UU.; validar retenciones con contador.

### Hotmart

- Usar **HotLink** oficial con `?src=clickya_<ubicacion>_<id>` para atribución.
- La cookie la define el productor (habitualmente 30–90 días).
- Comisiones en USD/BRL/EUR según el productor; retiro a cuenta local o Payoneer.
- Comprador argentino paga con **Mercado Pago**; los impuestos locales los cobra el medio de pago, fuera de Hotmart.
- Divulgación: “Enlace de afiliado” + `#Publicidad`.

### Argentina

- La publicidad debe ser **identificable** y no engañosa (Ley 24.240 arts. 4 y 8; Ley 22.802 art. 5). No hay ley específica de influencers vigente, pero el deber de información aplica igual.
- Si la publicación implica una oferta, la Resolución 12/2024 pide vigencia territorial/temporal y nombre, domicilio y CUIT del oferente. En afiliados, **dejar claro quién vende**: ClickYa vende el stock local; Amazon/Hotmart venden y responden por el producto externo.
- Devoluciones y garantía de productos externos: las gestiona la plataforma, no ClickYa. Ya está insinuado en `/envios`; hacerlo explícito en la ficha.
- **Fiscal**: las comisiones son ingresos. Si sos monotributista, entran en la categoría; para servicios al exterior, el contador definirá si corresponde factura E. Guardar reporte mensual: comisión bruta, fees, cotización y neto.

## 4. Arquitectura de información

Mantener el catálogo único, pero separar la experiencia:

- **Home**: hero + 3 bloques (“Stock local”, “Amazon”, “Cursos”) + 2–3 selecciones + buscador.
- **Landings por vertical** (URLs limpias, indexables):
  - `/local` → stock local con envío CABA/GBA.
  - `/amazon` → importados, copy “precio y envío se confirman en Amazon”.
  - `/cursos` → Hotmart, copy “acceso inmediato, pago con Mercado Pago”.
- **Categorías dentro de cada vertical** (`/amazon/tecnologia`, `/cursos/marketing`).
- **Selecciones curadas** (`/coleccion/setup-gamer`): 3–8 productos con un texto editorial, cada uno con su CTA y divulgación. Sirven para IG (“Top 3…”) y SEO.
- **“Mi lista” (opcional)**: guardar productos en `localStorage` y compartir la lista por URL. No es un carrito: es una wishlist con links salientes.
- **Carrito local**: se mantiene igual (transferencia/contra entrega).

## 5. Tracking y medición

Convención de nombres:

| Ubicación | `src` / `ascsubtag` |
|---|---|
| Card del catálogo | `web_card_<id>` |
| Ficha de producto | `web_detail_<id>` |
| Bio | `bio_<id>` |
| Telegram | `tg_<id>` |
| Selección | `sel_<slug>_<id>` |
| Historia/Reel (link en bio) | `ig_bio_<id>` |

Implementación:

- `integraciones.url_afiliada(producto, ubicacion)` arma el link directo y agrega el parámetro correcto (`?` o `&`).
- Clicks: link directo + `navigator.sendBeacon('/api/click/<id>', {src})` (no bloquea la navegación; si falla, el link igual funciona). Eximir esa ruta del CSRF.
- Dashboard: clicks por plataforma y **por ubicación**; top productos; EPC.
- Comisiones: tabla mensual manual (`mes, plataforma, usd_bruto, fees, neto`) cargada desde los reportes de Amazon/Hotmart. Con eso: **comisión real / clicks = EPC**.

## 6. Contenido y canales

- **Instagram**: 80 % stock local, 20 % afiliados. Formato “Top 3 / hallazgos” con link en bio a la selección. Divulgación en el caption: `#Publicidad` + “enlace de afiliado”. Nunca precios de Amazon.
- **Telegram**: link directo con `src=tg_<id>` y aviso de afiliado.
- **Bio**: tres bloques (local / Amazon / cursos) + selecciones; ya existe la base.
- **SEO**: guías “mejores X”, comparativas y selecciones; sin precios de Amazon, con divulgación.
- **WhatsApp**: para stock local. Para afiliados, mandar a la web/bio (no link de Amazon en el mensaje).

## 7. Roadmap

### Fase 0 — Cumplimiento y quick wins (1 día)
- Links directos con `ascsubtag`/`src`; helper en `integraciones.py`.
- Beacon de clicks y endpoint `/api/click/<id>`.
- Divulgación inline en card/ficha/bio + captions de Telegram e IG.
- Corregir “Envío a Argentina” en Hotmart y claims de stock/precio en captions.
- Archivos: `integraciones.py`, `tienda.py`, `templates/tienda/_card.html`, `producto.html`, `bio.html`, `contenido.py`, `instagram_api.py`.
- Aceptación: clic en card Amazon va directo a `amazon.*` con tag + `ascsubtag`; el click queda registrado; ningún texto promete envío/stock local para externos.

### Fase 1 — Landings y home (2–3 días)
- Rutas `/local`, `/amazon`, `/cursos`; nav y canonical.
- Home con 3 bloques y buscador.
- Ajustar `og:title/description` por vertical.
- Aceptación: cada vertical tiene URL propia, copy y disclaimer; el home no mezcla cards sin contexto.

### Fase 2 — Selecciones (3–4 días)
- Tablas `selecciones` y `seleccion_items`; admin CRUD; páginas públicas.
- Bloque de selecciones en home y bio.
- Aceptación: crear “Setup gamer” con 5 productos, publicarla y trackear `sel_...`.

### Fase 3 — Medición de ingresos (2 días)
- Clicks por ubicación en el dashboard.
- Tabla de comisiones mensuales + tarjeta “Comisiones del mes (USD)” y EPC.
- Aceptación: cargar el reporte de septiembre de Amazon/Hotmart y ver el neto y el EPC.

### Fase 4 — Contenido (continuo)
- Calendario: 2 posteos/día (1 local + 1 afiliado/curso 2–3 veces por semana).
- Reporte mensual: clicks, conversiones, comisiones, top selecciones.

## 8. Economía esperada (orden de magnitud)

- **Amazon**: comisión típica en tecnología 1–4 %. Con 175 clicks/mes y conversión 1–3 %: 2–5 pedidos; ticket USD 50 → **USD 2–10/mes**. No es el motor; sirve para catálogo y confianza.
- **Hotmart**: curso de USD 27 al 50 % = **USD 13,50 por venta**. Con 1–2 ventas/semana ya supera a Amazon. Prioridad comercial.
- Regla: no escalar pauta ni producción de contenido afiliado hasta tener EPC real de 60–90 días.

## 9. Riesgos

- **Cierre de cuenta Amazon** por redirecciones, precios o divulgación. Mitigación: Fase 0.
- **Reclamos de consumidor** por confundir quién vende. Mitigación: “vendido por Amazon/Hotmart” visible.
- **Impuestos**: comisiones del exterior; validar con contador y registrar cada cobro.
- **Stock/precio desactualizado** en Amazon: nunca mostrar precio propio; el usuario lo ve en destino.
- **Fatiga de contenido**: separar pilares y no publicar afiliados como si fuera stock local.

## 10. Decisiones y datos que necesito

1. ¿Aprobás la **Fase 0** (1 día) para dejar el circuito afiliado compliant?
2. **Tag de Amazon** (ej. `clickya-20`) y links completos (los `amzn.to` no siempre aceptan `ascsubtag`).
3. **Hotmart**: ID de afiliado y 3–5 productos iniciales (links, imágenes, comisión).
4. ¿Arrancamos con 3 selecciones? Propuesta: “Setup gamer”, “Casa inteligente”, “Cursos para emprender”.
5. ¿Mantenemos un solo dominio? (recomendado: sí).
6. ¿Querés “Mi lista” o alcanza con selecciones?

## 11. Anexo: de dónde sacar cada dato (implementado 20/10)

Estado: **Fase 0, 2 y 3 implementadas** (commit `0404ffc`). Fase 1 (landings propias) no.

### Tag de Amazon (Associates)
1. Amazon Associates → **SiteStripe** en la barra superior de cualquier producto.
2. Clic en **“Get Link”** → pestaña **“Full Link”** (no el corto `amzn.to`).
3. El link trae `?tag=clickya-20` (tu tag). Copiarlo completo.
4. Pegarlo en el producto como `link_afiliado`/`external_url`.
5. Opcional: cargar `AMAZON_TAG` en Railway; el sistema agrega el tag si falta.
6. La atribución por ubicación viaja en `ascsubtag` (`clickya_web_card_42`, `clickya_tg_42`, etc.).
7. **Comisiones**: Associates → *Reports* → *Commission Income* (mensual) → **Download CSV**.
   Impacto ~60 días; cargar el neto en `/contenido/afiliados`.

### Hotmart
1. No hay “ID de afiliado” aparte: el **HotLink** (`https://go.hotmart.com/A…`) ya identifica.
2. Hotmart → **Mercado** → buscar producto → **“Afiliarse”** → copiar **“Link de afiliado”**.
3. Pegarlo en el producto con plataforma `hotmart` y tipo `afiliado_digital`.
4. El sistema agrega `?src=clickya_<ubicacion>_<id>` para atribución.
5. **Comisiones**: Hotmart → *Ventas* → **“Informe de comisiones”** → exportar CSV (USD).
   Cargar bruto/fees/neto por mes en `/contenido/afiliados`.

### Selecciones
No requieren datos externos: se arman en `/selecciones` con productos ya cargados
y quedan públicas en `/coleccion/<slug>` (también aparecen en `/bio`).
