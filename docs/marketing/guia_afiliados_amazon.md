# Guía: Afiliarse a Amazon Associates y cargar productos en ClickYa

## Paso 0 — Crear la cuenta de afiliado (una sola vez)
1. Ir a <https://affiliate-program.amazon.com> → **Sign up**.
2. Completar datos (usar los datos de ClickYa, no personales si preferís).
3. En la parte del **sitio web/app**, poner `https://clickya.net`.
4. En "Cómo llegarás tráfico", marcar redes sociales + sitio propio.
5. Amazon te da un **ID de seguimiento (tracking ID)** ej. `clickyanet-20`.
   - Guardalo: es tu `?tag=` para todos los links.

### Paso 1 — Buscar el producto con "Ships to Argentina"
1. En Amazon, buscar el producto. Escribir "producto + amazon" si estás en Argentina.
2. En la ficha, verificar que diga **"Ships to Argentina"** (logística del producto).
   - Si dice que no envía, buscar la misma categoría con otro vendedor; si no, saltear.
3. Confirmar precio razonable bajo USD 400 (franquicia sin aranceles, solo IVA).

### Paso 2 — Generar el link afiliado
1. En tu panel de Associates, usar el **SiteStripe** (barra de herramientas en la página del producto).
2. Click en "Get link" → copiar la URL final (contiene `tag=clickyanet-20`).
   - Alternativa manual: copiar la URL del producto y agregarle `?tag=clickyanet-20` al final.
3. Guardar el link completo en el memo/notas (no perderlo).

### Paso 3 — Cargar en el panel de ClickYa
1. Abrir `https://clickya.net` → iniciar sesión.
2. Ir a **Productos → Nuevo producto**.
3. Llenar:
   - **Nombre**: "Amazon Kindle Paperwhite — Afiliado"
   - **Tipo producto**: `amazon_affiliate`
   - **Es afiliado**: Sí
   - **Imagen**: descargarla y subirla (o URL de la imagen)
   - **Link afiliado**: pegar el link del Paso 2
   - **Precio**: estimar en pesos con el dólar de referencia del día.
4. **Guardar**.

### Paso 4 — Publicar y medir
1. Verificar que el producto aparezca en la sección Amazon de la tienda y que el link redirija a Amazon.
2. Cada 15 días revisar en el panel de Associates qué links generaron clics y ventas.
3. Repetir: lo que más clics tiene, merece más exposición (post en redes).

### Errores comunes
- **Sin comisión**: el link no tiene tu tag, o el comprador no entra por tu link. Siempre abrir el link afiliado para ingresar a Amazon.
- **Producto que no envía**: si "Ships to Argentina" no aparece, la venta no se concreta. Verificar antes de publicar.
- **Precio mal estimado**: el precio en pesos es referencial; el cliente paga en USD a Amazon, no a vos. No negociar precios por el mensaje, aclarar que es affiliate.
