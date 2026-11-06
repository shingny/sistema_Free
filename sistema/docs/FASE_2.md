# Fase 2 — Panel de cocina y pedidos de salón (Sprint 3)

**Fecha:** 4 de noviembre de 2026  
**Estado:** completada y verificada  
**Alcance:** mesas, pedidos de salón, envío a cocina y panel `/cocina/`.

## 1. Objetivo

Incorporar la operación de salón y cocina al mismo sistema Django, reutilizando los modelos y servicios de `ventas`:

- Registrar pedidos de salón con mesa.
- Enviar el pedido a la cola de cocina.
- Permitir que cocina avance el pedido por sus estados.
- Mantener separados los accesos de dueño, caja y cocina.
- No implementar todavía el pedido por internet del cliente.

## 2. Modelo de datos

### Mesa

Se agregó el modelo `Mesa` en `apps/ventas/models.py`:

- `numero`: número único.
- `nombre`: nombre opcional; si está vacío se muestra `Mesa <número>`.
- `capacidad`: capacidad de la mesa.
- `activa`: permite ocultarla del POS sin borrar su historial.
- `creada`: fecha de creación.

La migración `ventas.0004_mesas_iniciales` crea las mesas 1 a 6 con capacidad 4.

### Pedido

Se agregó `Pedido.mesa` como llave foránea opcional a `Mesa`. Los pedidos para llevar quedan sin mesa; los pedidos de salón la requieren a nivel de servicio.

El modelo ya contaba con:

- `origen`: `para_llevar` o `salon`.
- `estado`: `pendiente`, `en_preparacion`, `listo`, `entregado`, `cancelado`.
- Número `P-AAAAMMDD-######`.
- Detalle histórico en `DetallePedido`.

## 3. Flujo de pedido de salón

1. El cajero abre el POS desde el panel de caja.
2. Selecciona la modalidad **Salón**.
3. Selecciona una mesa activa.
4. Agrega productos al carrito.
5. Puede elegir **Cobrar ahora** o dejar el pedido sin pago inmediato.
6. Al registrar:
   - Se crea el `Pedido` con `origen="salon"` y `mesa`.
   - Se crea la `Venta` vinculada.
   - Si no se cobró, la venta queda con estado de pago `pendiente` y sin `Pago`.
   - El pedido queda en estado `pendiente` y aparece en cocina.
7. Cocina avanza el pedido: `pendiente` → `en_preparacion` → `listo` → `entregado`.
8. Si quedó saldo pendiente, caja puede registrarlo después desde el detalle de la venta.

### Validaciones

- La modalidad debe ser `para_llevar` o `salon`.
- Un pedido de salón exige una mesa activa.
- Un pedido para llevar no acepta mesa.
- El pago es obligatorio para pedidos para llevar.
- El pago es opcional para pedidos de salón.
- Se mantienen las reglas existentes de descuentos, pagos parciales, métodos activos y saldo disponible.

## 4. Panel de cocina

Rutas:

- `/cocina/` — tablero de cocina.
- `/cocina/pedidos/<pk>/` — detalle del pedido.
- `/cocina/pedidos/<pk>/avanzar/` — cambio de estado por POST.

El tablero muestra tres columnas:

- **Pendientes**
- **En preparación**
- **Listos**

Los pedidos entregados o cancelados salen del tablero activo. Cada tarjeta muestra número, mesa u origen, cliente, hora, productos, cantidades, observaciones y total.

El avance de estado usa el servicio existente `cambiar_estado_pedido`, valida la transición y registra auditoría con el módulo `cocina`.

## 5. Permisos y accesos

Se agregó el módulo `cocina` con las acciones:

- `cocina.ver`
- `cocina.actualizar`

Asignación:

- Dueño: todos los permisos de forma dinámica.
- Administrador: 39 permisos explícitos, incluidos los de cocina.
- Jefe de cocina y cocinero: 5 permisos, incluidos `cocina.ver` y `cocina.actualizar`.
- Cajero: 12 permisos; no accede al panel de cocina.

Redirección después del login:

- Dueño/administrador → `/panel/`.
- Cajero → `/caja/`.
- Cocinero/jefe de cocina → `/cocina/`.

Accesos restringidos:

- Cajero no puede entrar a `/panel/` ni a `/cocina/`.
- Cocinero no puede entrar a `/panel/` ni a `/caja/`.
- Dueño/administrador pueden supervisar los tres paneles.

## 6. Interfaz

- `templates/base_cocina.html`: layout propio del panel de cocina, con clase `panel-cocina` y menú `menu_cocina`.
- `templates/cocina/tablero.html`: tablero de tres columnas.
- `templates/cocina/pedido_detalle.html`: detalle y acciones de estado.
- `static/css/app.css`: colores y estilos del panel de cocina, con adaptación móvil.
- POS de caja: selector de modalidad, selector de mesa y casilla **Cobrar ahora**.
- Listado y detalle de pedidos: columna y fila de mesa.

## 7. Archivos principales

- `apps/ventas/models.py`: `Mesa` y `Pedido.mesa`.
- `apps/ventas/services.py`: `crear_venta` con `origen` y `mesa`; pago opcional para salón.
- `apps/ventas/views.py`: POS, pedidos y detalle con mesa.
- `apps/ventas/urls.py` y `apps/ventas/urls_caja.py`: rutas de caja y compatibilidad.
- `apps/cocina/views.py`, `apps/cocina/urls.py`: tablero, detalle y avance.
- `apps/cuentas/permisos.py`: catálogo de permisos de cocina.
- `apps/cuentas/management/commands/inicializar.py`: asignación de permisos por rol.
- `apps/nucleo/context_processors.py`: `MENU_COCINA`, `menu_cocina` y `panel_base`.
- `apps/cuentas/views.py` y `apps/nucleo/views.py`: redirección por rol.
- `templates/base_cocina.html`, `templates/cocina/*`, `templates/ventas/pos.html`, `templates/ventas/pedidos.html`, `templates/ventas/pedido_detalle.html`.
- `static/css/app.css`.

## 8. Migraciones

- `cuentas.0003_alter_permiso_accion_alter_permiso_modulo`
- `ventas.0003_mesa_pedido_mesa`
- `ventas.0004_mesas_iniciales`

## 9. Pruebas

Se agregaron 8 pruebas en `apps/cocina/tests.py`:

- Venta de salón sin pago queda pendiente.
- Pedido de salón exige mesa.
- Cocina ve y avanza un pedido.
- Cajero recibe 403 en `/cocina/`.
- Cocinero recibe 403 en `/caja/`.
- Login de cocinero redirige a `/cocina/`.
- Dueño ve el panel de cocina.
- POS crea pedido de salón sin pago y renderiza modalidad/mesa.

Resultado: **80 pruebas OK** en la suite completa.

## 10. Decisiones y limitaciones

- El pago es opcional para salón para permitir cuentas abiertas; el cobro posterior se hace desde el detalle de la venta.
- El tablero de cocina incluye pedidos para llevar y de salón, porque ambos requieren preparación.
- Las mesas 1 a 6 se crean por migración; la administración visual de mesas queda para la siguiente iteración.
- El tablero se actualiza al recargar; no hay WebSockets ni notificaciones en tiempo real.
- No se implementó el pedido por internet del cliente.

## 11. Siguiente iteración sugerida

1. Pantalla de administración de mesas.
2. Actualización en tiempo real del tablero de cocina.
3. Panel público `/pedido/` para el cliente.
4. Inventario y disponibilidad por insumos.
5. Impresión térmica/fiscal y exportación de reportes.
