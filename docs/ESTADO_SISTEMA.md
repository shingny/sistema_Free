# Estado del sistema — Pollería

**Actualizado:** 5 de noviembre de 2026  
**Proyecto:** `D:\polleria sistema\sistema\PANEL ADMINISTRATIVO DEL DUEÑO`  
**Estado:** Fase 2 completa y Fase 3 en desarrollo. Paneles de dueño, caja, cocina y mesero operativos.

## 1. Resumen ejecutivo

El sistema es una sola aplicación Django con módulos internos que comparten usuarios, roles, permisos, productos, configuración, auditoría y servicios de ventas/caja. Ya están operativos:

- Panel administrativo del dueño.
- Panel de caja y ventas.
- Panel de cocina.
- POS con carrito, descuentos autorizados, pagos y ticket.
- Ventas para llevar y pedidos de salón con mesa.
- Envío de pedidos a cocina y seguimiento por estados.
- Apertura, movimientos y cierre de caja.
- Historial de ventas con filtros.
- Dashboard del dueño con métricas reales.
- Auditoría de operaciones sensibles.
- Separación visual y de rutas entre los paneles de dueño, caja y cocina.

**Verificación:** 162 pruebas automáticas aprobadas. `manage.py check` sin observaciones y sin migraciones pendientes.

## 2. Stack y entorno local

| Elemento | Estado |
|---|---|
| Python | 3.12.3 |
| Django | 5.2.19 |
| Base de datos local | SQLite (`db.sqlite3`) |
| Base de datos producción | MySQL/MariaDB en Alwaysdata vía PyMySQL |
| Despliegue web | Render Web Service (Gunicorn) |
| Archivos estáticos | WhiteNoise (`collectstatic`) |
| Zona horaria | America/Lima |
| Modo local | `DEBUG=True` |
| Servidor | Detenido; puerto 8000 libre |
| Usuario dueño local | `dueno` / `Polleria-Local-2026!` |

Para iniciar:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py inicializar
.\.venv\Scripts\python.exe manage.py runserver
```

## 3. Arquitectura

| App | Responsabilidad |
|---|---|
| `cuentas` | Usuario personalizado, roles, permisos, autenticación, perfil y gestión de usuarios |
| `catalogo` | Categorías y productos |
| `nucleo` | Configuración, auditoría, dashboard, menús, inicio y utilidades |
| `ventas` | Caja, turnos, mesas, ventas, pagos, pedidos, historial y reportes de ventas |
| `cocina` | Cola de preparación y cambios de estado de pedidos; consume los pedidos de `ventas` |

La comunicación entre paneles es directa mediante la misma base de datos, modelos y servicios. No se usan APIs internas ni proyectos separados. La app `cocina` no tiene modelos propios: opera sobre `Pedido` y `DetallePedido`.

## 4. Paneles actuales

### 4.1 Panel administrativo del dueño — `/panel/`

Incluye:

- Dashboard global con ventas del periodo, operaciones, efectivo, cobros electrónicos, cajas abiertas/cerradas, diferencias, pedidos en curso y ventas por cajero.
- Usuarios, roles y permisos.
- Productos y categorías.
- Configuración del negocio y logo.
- Supervisión de cajas y turnos.
- Métodos de pago.
- Auditoría de actividad.

Acceso: usuarios con permiso `dashboard.ver` (dueño y administrador).

### 4.2 Panel de caja y ventas — `/caja/`

Incluye:

- Inicio de caja: turno actual, ventas del día, pedidos en curso y accesos rápidos.
- Nueva venta / POS con modalidad para llevar o salón.
- Selección de mesa para pedidos de salón.
- Pedidos para llevar y pedidos de salón.
- Cobro del saldo pendiente de una venta de salón.
- Historial propio del cajero.
- Apertura de caja.
- Movimientos de caja.
- Cierre de caja.
- Detalle de venta, pagos, ticket y anulación según permisos.

Acceso: usuarios con permiso `ventas.ver` (cajero, administrador y dueño). El dueño y el administrador también pueden entrar a `/caja/` para supervisar u operar.

### 4.3 Panel de cocina — `/cocina/`

Incluye:

- Tablero con tres columnas: pendientes, en preparación y listos.
- Tarjetas con número de pedido, mesa u origen, cliente, hora, productos, cantidades y observaciones.
- Detalle del pedido.
- Avance de estado: pendiente → en preparación → listo → entregado.
- Auditoría de cada cambio de estado.
- Actualización visual diferenciada del panel de cocina.

Acceso: usuarios con permiso `cocina.ver`. Los cambios de estado requieren `cocina.actualizar`.

### 4.4 Rutas legadas — `/ventas/...`

Se conservan por compatibilidad. Usan la misma lógica, permisos y datos que `/caja/...`. Los enlaces internos del panel de caja apuntan al namespace `caja:`; el panel administrativo sigue usando `ventas:` para cajas y métodos de pago.

### 4.5 Panel mesero — `/mesero/`

- Incluye inicio, mesas, detalle de cuenta, rondas, solicitud de cobro, cierre, pedidos activos/listos e historial.
- Acceso: usuarios con permiso `mesas.ver` (mesero, cajero, administrador y dueño).

### 4.6 Panel pendiente

- `/pedido/` — Pedido por internet del cliente, previsto para una fase posterior.

## 5. Separación visual y de acceso

- `templates/base.html` es la base compartida.
- `templates/base_admin.html` define el panel administrativo con clase `panel-admin`, menú `menu_admin` y color institucional.
- `templates/base_caja.html` define el panel de caja con clase `panel-caja`, menú `menu_caja` y color diferenciado.
- `templates/base_cocina.html` define el panel de cocina con clase `panel-cocina`, menú `menu_cocina` y color cálido diferenciado.
- El context processor expone `panel_base`, `menu`, `menu_admin`, `menu_caja` y `menu_cocina` según el usuario y el namespace.
- Después del login:
  - Dueño/administrador → `/panel/`.
  - Cajero → `/caja/`.
  - Cocinero/jefe de cocina → `/cocina/`.
  - Usuarios sin dashboard, ventas ni cocina → inicio genérico.
- El dueño/administrador puede entrar a `/caja/` y `/cocina/`; el cajero no puede entrar a `/panel/` ni a `/cocina/`; el cocinero no puede entrar a `/caja/` ni a `/panel/`.
- El menú del cajero solo muestra sus módulos; no muestra usuarios, roles, configuración ni reportes globales.
- El menú de cocina solo muestra el tablero de cocina.

## 6. Funcionalidad implementada

### Autenticación y permisos

- Login con bloqueo temporal tras intentos fallidos.
- Contraseña temporal de un solo uso.
- 6 roles: Dueño, Administrador, Jefe de cocina, Cajero, Mesero y Cocinero.
- 52 permisos en el catálogo.
- Dueño con todos los permisos de forma dinámica.
- Administrador con 39 permisos explícitos.
- Cajero con 12 permisos: caja ver/abrir/mover/cerrar; categorías ver; pagos ver/registrar; pedidos ver/editar; productos ver; ventas ver/crear.
- Cocinero y jefe de cocina con 5 permisos: categorías ver, cocina actualizar, cocina ver, pedidos ver y productos ver.
- Validación de permisos en backend con respuesta 403 y auditoría del intento.

### Catálogo

- 6 categorías y 16 productos cargados en la base local.
- Productos activos de categorías activas son los únicos vendibles.
- Precio y nombre se copian a la venta como histórico.

### Mesas y pedidos de salón

- Modelo `Mesa` con número único, nombre opcional, capacidad, estado activo y fecha de creación.
- Mesas iniciales 1 a 6 creadas por migración de datos.
- El POS permite elegir modalidad **Para llevar** o **Salón**.
- En modalidad salón se exige una mesa activa.
- El pedido de salón puede crearse sin pago inmediato; la venta queda con estado de pago pendiente.
- Si se marca **Cobrar ahora**, se registra el primer pago en el mismo momento.
- El saldo pendiente puede cobrarse después desde el detalle de la venta.
- El pedido se crea en estado `pendiente` y aparece de inmediato en cocina.
- El pedido conserva número `P-AAAAMMDD-######`, mesa, cliente, observación y detalle histórico.

### Caja

- Caja principal `CAJA-01`.
- Un turno abierto por cajero y uno por caja.
- Apertura con monto inicial y observación.
- Movimientos de ingreso, egreso, venta y devolución.
- Efectivo esperado = monto inicial + ingresos/ventas en efectivo − egresos − devoluciones en efectivo.
- Tarjeta y transferencia no afectan el efectivo físico.
- Cierre con monto contado, diferencia y resumen inalterable desde la interfaz.
- Historial de turnos para supervisión.

### Ventas y pagos

- POS con categorías, búsqueda, productos, cantidades, carrito, subtotal, descuento, total y modalidad para llevar/salón.
- Venta con número único `V-AAAAMMDD-######` y token UUID contra doble envío.
- Detalle histórico de productos, precios y cantidades.
- Pago parcial permitido y configurable.
- Métodos iniciales: Efectivo, Tarjeta, Transferencia y Yape/Plin.
- Transferencia y Yape/Plin quedan pendientes de verificación hasta que dueño/administrador las confirme.
- Pagos pendientes reservan saldo para evitar sobrepagos.
- Estados de pago independientes del estado de preparación del pedido.
- Anulación con motivo, devolución en efectivo cuando corresponde y pagos reembolsados.
- Ticket HTML imprimible.

### Cocina

- Tablero con pedidos pendientes, en preparación y listos.
- Los pedidos entregados o cancelados salen del tablero activo.
- Avance de estado con validación de transiciones.
- Solo usuarios con `cocina.actualizar` pueden cambiar estados.
- Cada cambio se registra en auditoría con el módulo `cocina`.
- El detalle muestra mesa u origen, cliente, productos, cantidades, observaciones y total.
- El tablero se actualiza al recargar; no se implementó todavía un canal en tiempo real.

### Historial y dashboard

- Historial con filtros por fecha, cajero, número de venta, método de pago y estado.
- El cajero solo ve sus ventas; dueño/administrador ven todas.
- Dashboard con métricas reales del periodo seleccionado.
- Auditoría de ventas, descuentos, pagos, verificaciones, anulaciones, caja, pedidos, cocina y métodos de pago.

## 7. Datos iniciales y estado de la base local

| Dato | Cantidad / valor |
|---|---|
| Usuarios locales | 1 (`dueno`) |
| Roles | 6 |
| Permisos | 44 |
| Categorías | 6 |
| Productos | 16 |
| Mesas | 6 (mesas 1 a 6, capacidad 4) |
| Cajas | 1 activa (`CAJA-01`, Caja principal) |
| Métodos de pago | 4 activos (Efectivo, Tarjeta, Transferencia, Yape/Plin) |
| Ventas locales | 0 |
| Turnos históricos | 2 |
| Pedidos locales | 0 |
| Pagos locales | 0 |

No hay un usuario cajero ni un usuario de cocina de demostración en la base local; pueden crearse desde el panel del dueño.

## 8. Migraciones aplicadas

- `cuentas.0001_initial`
- `cuentas.0002_alter_permiso_accion_alter_permiso_modulo`
- `cuentas.0003_alter_permiso_accion_alter_permiso_modulo`
- `nucleo.0001_initial`
- `nucleo.0002_configuracion_permitir_pago_parcial`
- `ventas.0001_initial`
- `ventas.0002_datos_iniciales`
- `ventas.0003_mesa_pedido_mesa`
- `ventas.0004_mesas_iniciales`
- `ventas.0005_pedido_prioridad_pedido_ronda_cuentamesa_and_more`
- `ventas.0006_incidenciacocina_estado_incidenciacocina_observacion_dueno`

No hay migraciones pendientes.

## 9. Pruebas y verificación

- Suite completa: **162 pruebas OK**.
- Módulo de ventas/caja: **22 pruebas**.
- Módulo de cocina: **8 pruebas**.
- `manage.py check`: sin observaciones.
- `manage.py makemigrations --check --dry-run`: sin cambios.
- Pruebas de paneles: login redirige según rol; dueño entra a `/panel/`, `/caja/` y `/cocina/`; cajero entra a `/caja/` y recibe 403 en `/panel/` y `/cocina/`; cocinero entra a `/cocina/` y recibe 403 en `/caja/`; las bases visuales `panel-admin`, `panel-caja` y `panel-cocina` se renderizan correctamente.
- Pruebas de salón: el pedido exige mesa, puede quedar pendiente de pago, aparece en cocina y avanza de estado.

## 10. Limitaciones actuales

- No existe todavía el pedido por internet del cliente (`/pedido/`).
- Las mesas se administran visualmente desde `/ventas/mesas/` (dueño/administrador).
- La actualización se realiza por polling cada 10 segundos en cocina y en el detalle de cuenta del mesero; no se usan WebSockets.
- No hay control de inventario ni descuento automático de stock.
- No hay integración con impresora fiscal; el ticket es HTML imprimible.
- No hay exportación de reportes de ventas/caja en esta fase.
- La base local solo tiene al dueño; los usuarios operativos deben crearse desde el panel.
- El servidor no está en producción ni corriendo actualmente.

## 11. Siguiente fase recomendada

**Fase 3 — Pedido por internet del cliente y administración de mesas:**

1. Crear el panel público `/pedido/` con carta, carrito y seguimiento.
2. Agregar administración visual de mesas: crear, editar, capacidad y activar/desactivar.
3. Incorporar notificaciones o actualización en tiempo real para cocina y caja.
4. Añadir control de inventario y disponibilidad por insumos.
5. Evaluar impresión térmica/fiscal y exportación de reportes.
6. Mantener la misma base de datos y los servicios compartidos.

El sistema queda documentado y verificado. La Fase 2 está cerrada; la Fase 3 requiere confirmación.
