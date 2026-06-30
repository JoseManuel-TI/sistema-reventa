# 🚀 ClickYa — Salir al mercado

## Identidad de marca

| Elemento | Valor |
|---|---|
| **Nombre** | ClickYa |
| **Eslogan** | Todo · Rápido · Fácil |
| **Colores** | Azul `#2563eb` · Verde `#059669` |
| **Logo** | `static/brand/logo.svg` |
| **Instagram** | [@clickya.ar](https://www.instagram.com/clickya.ar/) |
| **WhatsApp** | `https://wa.me/549XXXXXXXXX` |
| **Dominio** | `clickya.com.ar` |

---

## Checklist de salida

### 1. 🔧 Infraestructura (prioridad alta)

- [ ] **VPS** — Contratar Hostinger KVM 1 (~$5 USD/mes) o DigitalOcean
- [ ] **Dominio** — Comprar `clickya.com.ar` en Nic.ar (~$800/año)
- [ ] **HTTPS** — Configurar Let's Encrypt con Certbot (lo hacemos juntos)
- [ ] **Deploy app** — Subir el código, instalar dependencias, correr Flask con systemd
- [ ] **MP Webhook** — Actualizar `MP_WEBHOOK_BASE` con el dominio real

### 2. 📱 Redes sociales

| Red | Handle | Qué publicar |
|---|---|---|
| **Instagram** | [@clickya.ar](https://www.instagram.com/clickya.ar/) | Cards de productos (generadas en `/exportar/instagram`) |
| **WhatsApp Business** | `549XXXXXXXXX` | Catálogo, respuestas automáticas |
| **TikTok** (opcional) | `@clickya.ar` | Reels de productos, unboxing, entregas |

### 3. 📸 Contenido semanal

- [ ] Publicar **3-4 cards de productos** (formato 9:16) desde `/exportar/instagram`
- [ ] Compartir **stories** con productos nuevos
- [ ] Agregar productos al catálogo de WhatsApp Business

### 4. ⚙️ Sistema

- [ ] Marcar productos como **publicados** desde `/productos` para que aparezcan en la tienda
- [ ] Ajustar `comision_mp_porcentaje` en `/precios` según el medio de pago
- [x] Probar flujo completo de compra desde `/tienda` ✅ (local con MP token funcional)
- [x] Verificar marca ClickYa en catálogo, admin, calculadora y cards IG ✅
- [ ] Productos: revisar cuáles marcar como `publicar=1` para visibilidad en tienda
- [ ] Ajustar WhatsApp link real en `/configuracion`

---

## Flujo operativo diario

```
1. Llega pedido → suena notificación
2. Preparás el producto
3. Entregás (moto / punto de encuentro)
4. Marcás como entregado en /pedidos
5. MP acredita el pago a tu cuenta
```

---

## Herramientas útiles

| Herramienta | Para qué |
|---|---|
| [UptimeRobot](https://uptimerobot.com) | Monitorear que la app no se caiga (gratis) |
| [Nic.ar](https://nic.ar) | Comprar dominio .com.ar |
| [Canva](https://canva.com) | Editar las cards de Instagram |
| [Google Analytics](https://analytics.google.com) | Medir tráfico de la tienda |

---

## Contacto y soporte

- **MP Soporte:** `https://www.mercadopago.com.ar/ayuda` (para temas de pagos)
- **Hostinger:** Chat en vivo (para temas del VPS)
- **Este proyecto:** Documentación en `docs/`
