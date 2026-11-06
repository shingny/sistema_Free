# Sprint 2 — Caja y ventas

## 1. Objetivo
Incorporar al panel existente el trabajo diario del cajero: apertura y cierre de caja, venta para llevar,
cobros, verificación de transferencias, historial de ventas, pedidos y supervisión del dueño. Se reutilizan
los usuarios, roles, permisos, productos y la configuración creados en el Sprint 1.

## 2. Arquitectura
Se agregó la app `apps.ventas` al mismo proyecto Django. No se creó un sistema paralelo.

| App | Responsabilidad |
|---|---|
| `cuentas` | Usuarios, roles, permisos y autenticación |
| `catalogo` | Categorías y productos disponibles |
| `nucleo` | Configuración, auditoría, dashboard, menú y utilidades |
| `ventas` | Caja, turnos, ventas, pagos, pedidos, historial y reportes del dueño |

- La base local de desarrollo es SQLite; la configuración de producción puede usar MySQL.
- `ATOMIC_REQUESTS` sigue activo: la venta, sus detalles, el pago y el movimiento de caja se guardan en una sola transacción.
- Todo movimiento sensible se registra en `Auditoria` con usuario, fecha, acción, entidad y descripción.

## 3. Modelo de datos
- `Caja(nombre, codigo, activa)`: caja física o lógica. El sistema parte con **Caja principal** (`CAJA-01`).
- `MetodoPago(codigo, nombre, afecta_efectivo, requiere_verificacion, activo, orden)`: medios configurables.
  Se inicializan Efectivo, Tarjeta, Transferencia y Yape/Plin.
- `TurnoCaja(caja, usuario, estado, monto_inicial, observacion_apertura, fecha_cierre, monto_contado,
  efectivo_esperado, diferencia, observacion_cierre, cerrado_por)`:
  - Solo puede existir **un turno abierto por cajero** y **uno por caja** (restricciones condicionales en base de datos).
  - El turno cerrado conserva el cálculo y no admite nuevos movimientos.
- `Pedido(numero, origen, estado, cliente, telefono, observacion, total, creado_por)`:
  - Origen `para_llevar` en Sprint 2; `salon` queda preparado para el Sprint 3.
  - Estados: pendiente, en preparación, listo, entregado y cancelado.
- `DetallePedido`: copia histórica del producto, nombre, precio, cantidad y subtotal.
- `Venta(numero, token, turno, cajero, pedido, cliente, subtotal, descuento, total, estado_pago, estado,
  observacion, descuento_motivo, descuento_autorizado_por, anulada_por, motivo_anulacion, fecha_anulacion)`:
  - Número único `V-AAAAMMDD-######`; token UUID para evitar ventas duplicadas por doble clic.
  - Estados de pago: pendiente, parcial, pagado y reembolsado.
  - Estados de venta: registrada y anulada. Una venta anulada no se elimina.
- `DetalleVenta`: copia histórica de nombres y precios al momento de vender.
- `Pago(venta, metodo, monto, referencia, estado, creado_por, verificado_por, fecha_verificacion)`:
  - Efectivo y tarjeta se registran como verificados.
  - Transferencia, Yape/Plin y otros medios configurados quedan **pendientes de verificación**.
  - Un pago pendiente no cuenta para el saldo pagado ni para el efectivo de caja.
- `MovimientoCaja(turno, tipo, monto, afecta_efectivo, metodo_pago, venta, pago, descripcion,
  autorizado_por, creado_por)`:
  - Tipos: apertura, venta en efectivo, ingreso, egreso y devolución.
  - El efectivo esperado se calcula como:
    `monto inicial + ventas/ingresos en efectivo - egresos - devoluciones en efectivo`.
  - Tarjeta y transferencia no afectan el efectivo físico.

## 4. Reglas de negocio
1. El cajero debe abrir su turno antes de vender. No puede vender desde el turno de otro usuario.
2. El monto inicial se registra al abrir; la apertura crea un movimiento de caja.
3. El POS solo muestra productos activos de categorías activas (`Producto.objects.disponibles()`).
4. Los precios y nombres se toman del servidor y se guardan como copia histórica en la venta.
5. **Pago parcial habilitado por defecto** desde `Configuracion.permitir_pago_parcial`. El dueño puede desactivarlo.
6. El primer pago se registra al confirmar la venta; se pueden agregar pagos posteriores desde el detalle.
7. Una transferencia no se considera cobrada porque el cajero la marque: queda pendiente hasta que el dueño o un
   administrador la verifique. También puede rechazarse.
8. Los descuentos requieren permiso `ventas.descuento` y motivo; solo dueño/administrador los autorizan.
9. La anulación requiere permiso `ventas.anular` y motivo. Si hubo pagos en efectivo verificados, se registra una
   devolución en la caja; los pagos quedan reembolsados. La venta y el pedido no se eliminan.
10. El cierre de caja compara el efectivo contado con el esperado y guarda la diferencia. No se puede reabrir un turno cerrado.
11. El cajero solo ve sus propias ventas y su caja. Los reportes globales y la supervisión de todas las cajas
    requieren permisos de dueño/administrador.
12. Los cambios de estado del pedido siguen transiciones controladas: pendiente → en preparación → listo → entregado.
    Cancelar un pedido con venta asociada también anula la venta.

## 5. Permisos nuevos
| Módulo | Acciones |
|---|---|
| `ventas` | ver, crear, anular, descuento, reportes |
| `pagos` | ver, registrar, verificar, reembolsar |
| `caja` | ver, abrir, mover, cerrar, supervisar |
| `pedidos` | ver, editar, cancelar |
| `metodos_pago` | ver, crear, editar, desactivar |

Permisos iniciales:
- **Cajero:** productos/categorías ver; ventas ver/crear; pagos ver/registrar; caja ver/abrir/mover/cerrar;
  pedidos ver/editar.
- **Administrador:** todos los permisos nuevos, incluida verificación de pagos, anulación, descuentos y supervisión.
- **Dueño:** todos los permisos por su rol jerárquico.
- `inicializar` es idempotente y ahora **agrega** los permisos base que falten a los roles existentes, sin quitar
  los que el dueño haya configurado.

## 6. Flujos y rutas
| Ruta | Nombre | Uso |
|---|---|---|
| `/ventas/` | `ventas:inicio` | Inicio del cajero: turno, ventas del día y pedidos en curso |
| `/ventas/nueva/` | `ventas:nueva_venta` | POS con categorías, productos, carrito y cobro |
| `/ventas/historial/` | `ventas:historial` | Historial con filtros por fecha, cajero, número, método y estado |
| `/ventas/<id>/` | `ventas:venta_detalle` | Detalle, pagos, verificación, anulación y movimientos |
| `/ventas/<id>/ticket/` | `ventas:venta_ticket` | Ticket imprimible |
| `/ventas/pedidos/` | `ventas:pedidos` | Pedidos para llevar y sus estados |
| `/ventas/caja/abrir/` | `ventas:caja_abrir` | Apertura de turno |
| `/ventas/caja/movimientos/` | `ventas:caja_movimientos` | Ingresos, egresos y efectivo esperado |
| `/ventas/caja/cerrar/` | `ventas:caja_cerrar` | Cierre y resumen inalterable |
| `/ventas/cajas/` | `ventas:cajas` | Supervisión de turnos (dueño/administrador) |
| `/ventas/metodos-pago/` | `ventas:metodos_pago` | Configuración de medios de pago |

## 7. Dashboard del dueño
El dashboard ahora muestra datos reales del periodo seleccionado:
- total vendido y número de operaciones;
- cobrado en efectivo y cobrado electrónico (solo pagos verificados);
- cajas abiertas y cierres del periodo;
- diferencia total de caja y cantidad de turnos con diferencia;
- pedidos en curso;
- ventas por cajero.

## 8. Pruebas
- `apps/ventas/tests.py`: 22 pruebas funcionales de apertura, cierre, venta completa, pago parcial, reserva de saldo
  con pagos pendientes, transferencia pendiente y verificación, producto inactivo, descuentos, auditoría del
  descuento, anulación con devolución, permisos del cajero, historial por cajero, dashboard, estados de pedido,
  cancelación con anulación y renderizado de las pantallas principales.
- Suite completa: **72 pruebas OK** (`python manage.py test`).
- `manage.py check` sin observaciones.

## 9. Puesta en marcha local
```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py inicializar
.\.venv\Scripts\python.exe manage.py runserver
```
La migración `ventas.0002_datos_iniciales` crea la Caja principal y los métodos de pago iniciales.
El dueño local de prueba es `dueno` / `Polleria-Local-2026!`.

## 10. Decisiones y límites
- El pago parcial está permitido; el pago mixto se resuelve registrando pagos adicionales desde el detalle de la venta.
- No se implementó todavía el pedido por internet del cliente ni el pedido de salón completo; el modelo `Pedido`
  y su origen `salon` quedan preparados para el Sprint 3.
- No hay control de inventario ni descuento de stock.
- No se integra una impresora fiscal; el ticket es HTML imprimible desde el navegador.
- No se eliminan ventas, pagos ni cierres: se anulan y se conserva el historial.
- La configuración de métodos de pago permite agregar otros medios y definir si afectan el efectivo o requieren verificación.

## 11. Siguiente sprint
- Pedidos de salón, mesas y vinculación con cocina.
- Actualización de estados desde cocina y pantalla de preparación.
- Pedido por internet del cliente.
- Reportes históricos más amplios y exportaciones de ventas/caja.

## 12. Paneles separados (Fase 1)
La misma base de datos y los mismos servicios se presentan ahora en ventanas independientes:

| Panel | Ruta | Usuario | Contenido |
|---|---|---|---|
| Administrativo | `/panel/` | Dueño / administrador | Dashboard global, usuarios, roles, productos, categorías, configuración, cajas y métodos de pago |
| Caja y ventas | `/caja/` | Cajero / dueño / administrador | Inicio de caja, POS, pedidos, historial propio, apertura, movimientos y cierre |
| Legado | `/ventas/...` | Cajero / dueño / administrador | Se conserva por compatibilidad; usa la misma lógica y permisos |

- El inicio de sesión redirige automáticamente: dueño/administrador a `/panel/`, cajero a `/caja/`.
- El dueño y el administrador pueden entrar a `/caja/`; el cajero no puede entrar a `/panel/` ni a módulos administrativos.
- Cada panel tiene su propia plantilla base (`base_admin.html` y `base_caja.html`), menú y color; comparten `base.html` para la estructura común.
- La comunicación es directa mediante la base de datos, modelos y servicios compartidos; no se usan APIs entre paneles.
- Las rutas `/cocina/` y `/pedido/` quedan para los siguientes sprints.
- Pruebas actuales: 22 pruebas funcionales de caja/ventas y 72 pruebas totales.
