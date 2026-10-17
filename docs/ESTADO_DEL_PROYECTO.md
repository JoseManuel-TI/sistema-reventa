# Estado del proyecto — 2026-09-18

La descripción operativa actual está en [README.md](../README.md).

Implementado: catálogo, administración con contraseña y protección CSRF, carrito, pedidos por transferencia bancaria, reserva transaccional de stock, cancelación con reposición, privacidad del detalle de pedidos, afiliados con seguimiento de clics, exportaciones y programación de contenido.

El checkout no utiliza Mercado Pago. La confirmación del pago es manual después de comprobar la acreditación bancaria. Las columnas históricas de ese proveedor se conservan en bases existentes para no borrar datos, pero no se usan en la aplicación.

La capa PostgreSQL utiliza cursores y adapta parámetros; las migraciones soportan instalaciones anteriores. Configuración, imágenes y calendario siguen necesitando un volumen persistente. El arranque no debe sobrescribir el catálogo existente.

No confundir estos cambios locales con un despliegue confirmado. Ver README para iniciar, probar, configurar almacenamiento y operar pedidos.
