# Plan Fase 3 — Sprint 3: Mesero, mesas, cocina avanzada y tiempo real

**Fecha de planificación:** 4 de noviembre de 2026  
**Estado:** En desarrollo (implementación parcial avanzada). Base actual: Fase 2 completada y verificada; Fase 3 en progreso.  
**Base actual:** Fase 2 (Sprint 3 parcial) completada y verificada: paneles de dueño, caja y cocina operativos, 80 pruebas OK.

---

## 1. Resumen ejecutivo

La Fase 2 dejó operativo el flujo caja → cocina para pedidos para llevar y de salón, incluyendo mesas básicas (1 a 6), POS con modalidad para llevar/salón, envío a cocina y avance de estados.  
La Fase 3 (Sprint 3) completa el MVP definido en `SPRINT 3.txt`: incorpora el **panel del mesero**, la **administración visual de mesas**, las **cuentas de atención con rondas**, la **supervisión del dueño sobre pedidos**, las **modificaciones y anulaciones controladas**, y una **estrategia de actualización en tiempo real**.

El pedido por internet del cliente (`/pedido/`) se mantiene **fuera del MVP**, tal como indican `identidad y arquitectura del sistema.txt` y `SPRINT 3.txt`.

---

## 2. Estado actual verificado

| Elemento | Valor |
|---|---|
| Pruebas automáticas | 80 OK (22 ventas/caja, 8 cocina, resto Sprint 1) |
| `manage.py check` | Sin observaciones |
| Migraciones | Sin cambios pendientes |
| Paneles | `/panel/`, `/caja/`, `/cocina/` |
| Mesas | 6 mesas fijas (1 a 6, capacidad 4), creadas por migración; sin administración visual |
| Roles | 6 (Dueño, Administrador, Jefe de cocina, Cajero, Mesero, Cocinero) |
| Permisos | 44 (catálogo actual; se ampliará) |
| Tiempo real | No implementado (solo recarga manual) |
| Panel mesero | No existe |
| Modificaciones por rondas | No implementado |
| Supervisión de pedidos del dueño | Parcial (dashboard muestra pedidos abiertos) |

---

## 3. Objetivo de la Fase 3

Implementar la operación completa de salón y cocina desde el punto de vista del mesero y del dueño, manteniendo una sola base de datos, los servicios compartidos y la independencia entre estado de preparación y estado de pago.

Resultado esperado: demostrar el flujo completo desde que el cliente solicita un pedido en salón hasta que lo recibe y paga, incluyendo cocina, caja, mesero y supervisión del dueño.

---

## 4. Alcance

### Incluye

1. Administración visual de mesas (crear, editar, capacidad, activar/desactivar).
2. Panel del mesero optimizado para tablet/celular.
3. Apertura de cuenta de atención por mesa, con control de concurrencia.
4. Registro de pedidos de salón desde el mesero.
5. Agregado de productos a una cuenta existente, con rondas identificables.
6. Mejora del panel de cocina (prioridad, tiempo transcurrido, observaciones, historial, productos agotados, incidencias).
7. Actualización en tiempo real o equivalente (polling) para cocina, mesero y caja.
8. Integración consolidada de pedidos para llevar (ya existente, con ajustes de notificación).
9. Modificaciones y anulaciones controladas con auditoría.
10. Supervisión del dueño sobre pedidos (estados, tiempos, modalidades, actividad).
11. Independencia de estados de preparación y pago (ya existente, se mantiene).

### Fuera de alcance (se mantiene así)

- Pedido por internet del cliente (`/pedido/`).
- Control de inventario por insumos y descuento automático de stock.
- Impresora fiscal/termica; el ticket sigue siendo HTML imprimible.
- Exportación avanzada de reportes (se evalúa en fase posterior).
- WebSockets obligatorios (se permite polling como equivalente).

---

## 5. Roles, permisos y menús

### 5.1 Permisos a agregar al catálogo (`apps/cuentas/permisos.py`)

Agregar módulo `mesas` y ampliar `pedidos`/`cocina`:

| Módulo | Acciones nuevas |
|---|---|
| `mesas` | `ver`, `gestionar`, `abrir`, `cerrar` |
| `pedidos` | `autorizar_cancelacion` (además de `ver`, `editar`, `cancelar`) |
| `cocina` | `reportar_agotado`, `registrar_incidencia`, `ver_historial` |
| `reportes` (opcional) | `ver_pedidos` para supervisión del dueño |

### 5.2 Asignación por rol (`inicializar`)

| Rol | Permisos adicionales |
|---|---|
| Mesero | `mesas.ver`, `mesas.abrir`, `mesas.cerrar`, `pedidos.ver`, `pedidos.editar`, `pedidos.cancelar` (solo propios), `cocina.ver` |
| Cocinero / Jefe de cocina | `cocina.ver`, `cocina.actualizar`, `cocina.reportar_agotado`, `cocina.registrar_incidencia`, `cocina.ver_historial`, `pedidos.ver` |
| Cajero | mantiene los actuales; agrega `mesas.ver` |
| Dueño / Administrador | todos los permisos nuevos |

### 5.3 Menús

- `MENU_MESERO` (nuevo): Inicio, Mesas, Nuevo pedido, Pedidos activos, Pedidos listos, Historial, Mi perfil.
- `MENU_ADMIN`: agregar "Mesas" y "Pedidos (supervisión)".
- `MENU_COCINA`: agregar "Historial", "Productos agotados".
- `MENU_CAJA`: agregar "Mesas" (solo visualización).

---

## 6. Modelo de datos propuesto

### 6.1 Nuevos modelos

#### `CuentaMesa` (atención abierta de una mesa)

```python
class CuentaMesa(models.Model):
    ESTADOS = [
        ("abierta", "Abierta"),
        ("cobro_solicitado", "Cobro solicitado"),
        ("cerrada", "Cerrada"),
        ("cancelada", "Cancelada"),
    ]
    mesa = ForeignKey(Mesa, on_delete=PROTECT, related_name="cuentas")
    mesero = ForeignKey(Usuario, on_delete=PROTECT, related_name="cuentas_abiertas")
    estado = CharField(..., default="abierta")
    cliente_nombre = CharField(blank=True)
    observacion = CharField(blank=True)
    venta = OneToOneField(Venta, null=True, blank=True, on_delete=PROTECT, related_name="cuenta_mesa")
    abierta = DateTimeField(auto_now_add=True)
    cerrada = DateTimeField(null=True, blank=True)

    Meta:
        constraints = [
            UniqueConstraint(fields=["mesa"], condition=Q(estado__in=["abierta", "cobro_solicitado"]),
                             name="cuenta_abierta_por_mesa")
        ]
```

#### `IncidenciaCocina`

```python
class IncidenciaCocina(models.Model):
    TIPOS = [("producto_agotado", "Producto agotado"), ("incidencia", "Incidencia")]
    pedido = ForeignKey(Pedido, null=True, blank=True, on_delete=SET_NULL, related_name="incidencias")
    producto = ForeignKey(Producto, null=True, blank=True, on_delete=SET_NULL)
    tipo = CharField(...)
    descripcion = CharField(max_length=300)
    creado_por = ForeignKey(Usuario, on_delete=PROTECT)
    creado = DateTimeField(auto_now_add=True)
```

### 6.2 Cambios a modelos existentes

#### `Pedido`

- Agregar `cuenta = ForeignKey(CuentaMesa, null=True, blank=True, on_delete=PROTECT, related_name="pedidos")`.
- Agregar `ronda = PositiveSmallIntegerField(default=1)`.
- Mantener `mesa` por compatibilidad (para salón se sincroniza con `cuenta.mesa`).
- Mantener `estado` actual. Opcional: agregar `prioridad` (`normal`, `alta`, `urgente`) para cocina.

#### `Venta`

- Agregar `cuenta = ForeignKey(CuentaMesa, null=True, blank=True, on_delete=PROTECT, related_name="venta")` (o OneToOne).
- Mantener `pedido` para para llevar.
- Para salón, la venta agregada se vincula a la cuenta; los pedidos/rondas se vinculan a la cuenta.

#### `Mesa`

- Sin cambios estructurales obligatorios. El estado (libre/ocupada) se deriva de la existencia de una `CuentaMesa` abierta o pedidos no terminados.
- Opcional: agregar `ubicacion` o `zona` (no prioritario).

### 6.3 Migraciones esperadas

- `ventas.0005_cuenta_mesa`
- `ventas.0006_pedido_cuenta_ronda_prioridad`
- `ventas.0007_venta_cuenta`
- `ventas.0008_incidencia_cocina`
- Datos iniciales: mantener mesas 1 a 6.

---

## 7. Flujos principales

### 7.1 Apertura de mesa

1. Mesero entra a "Mesas".
2. Selecciona una mesa libre.
3. Sistema crea `CuentaMesa` en transacción con bloqueo de la mesa.
4. Si ya existe cuenta abierta, se muestra la cuenta existente (sin duplicar).
5. Mesa pasa a estado "ocupada".

### 7.2 Registro de pedido de salón (primera ronda)

1. Mesero selecciona productos, cantidades y observaciones.
2. Confirma.
3. Sistema crea `Pedido` (ronda 1) vinculado a la cuenta, con estado `pendiente`.
4. Si no existe venta agregada, crea `Venta` vinculada a la cuenta, estado de pago `pendiente`.
5. Se crean `DetallePedido` y `DetalleVenta` (agregados).
6. Cocina recibe el pedido sin recarga manual (polling/WebSocket).
7. Mesero consulta estado.

### 7.3 Agregar productos a cuenta existente

1. Mesero agrega productos a una cuenta abierta.
2. Si el último pedido de la cuenta sigue `pendiente` (no iniciado en cocina), se actualizan sus detalles.
3. Si ya está en preparación o listo, se crea un nuevo `Pedido` (ronda N+1) identificable.
4. Se actualiza la venta agregada (totales y detalles).
5. Se registra auditoría con usuario, fecha, hora, productos y motivo (si aplica).

### 7.4 Cocina

1. Recibe pedidos automáticamente (polling).
2. Ve número, modalidad, mesa, hora, productos, cantidades, observaciones, prioridad y tiempo transcurrido.
3. Avanza estados: pendiente → en preparación → listo → entregado.
4. Puede reportar producto agotado o incidencia.
5. No accede a precios, cobros ni administración.

### 7.5 Tiempo real

1. Mesero registra pedido → backend guarda → cocina recibe sin recarga.
2. Cocina marca listo → backend actualiza → mesero recibe notificación.
3. Caja consulta estado.
4. Dueño supervisa.
5. La base de datos conserva el estado verdadero; las notificaciones son solo avisos.

### 7.6 Solicitud de cobro

1. Mesero solicita cobro (cuenta pasa a `cobro_solicitado`).
2. Caja ve la cuenta y su venta agregada.
3. Caja registra pagos (parciales o completos) sobre la venta.
4. Al pagar y entregar, la cuenta se cierra y la mesa se libera.

### 7.7 Anulaciones

1. Solo usuarios con permisos (`pedidos.cancelar`, `ventas.anular` según caso).
2. Se solicita motivo, usuario, fecha y hora.
3. Si el pedido está en preparación, se requiere autorización y se notifica a cocina.
4. Si existe pago, se ejecuta devolución/ajuste.
5. Nunca se elimina físicamente el historial.

---

## 8. Arquitectura y rutas propuestas

### 8.1 Nuevas rutas

| Ruta | Nombre | Uso |
|---|---|---|
| `/mesero/` | `mesero:inicio` | Inicio del mesero |
| `/mesero/mesas/` | `mesero:mesas` | Visualización y apertura de mesas |
| `/mesero/mesas/<id>/abrir/` | `mesero:mesa_abrir` | Abrir cuenta |
| `/mesero/cuentas/<id>/` | `mesero:cuenta_detalle` | Cuenta abierta, productos y rondas |
| `/mesero/cuentas/<id>/agregar/` | `mesero:cuenta_agregar` | Agregar productos (nueva ronda si aplica) |
| `/mesero/cuentas/<id>/cobrar/` | `mesero:cuenta_cobrar` | Solicitar cobro |
| `/mesero/cuentas/<id>/cerrar/` | `mesero:cuenta_cerrar` | Cerrar cuenta y liberar mesa |
| `/mesero/pedidos/activos/` | `mesero:pedidos_activos` | Pedidos activos del mesero |
| `/mesero/pedidos/listos/` | `mesero:pedidos_listos` | Pedidos listos para entregar |
| `/mesero/historial/` | `mesero:historial` | Historial del mesero |
| `/admin/mesas/` o `/panel/mesas/` | `ventas:mesas` | Administración visual de mesas |
| `/panel/pedidos/` | `nucleo:pedidos_supervision` | Supervisión del dueño |
| `/cocina/historial/` | `cocina:historial` | Historial de cocina |
| `/cocina/productos-agotados/` | `cocina:agotados` | Productos agotados e incidencias |
| `/api/...` (polling) | varios | Endpoints JSON para actualización |

### 8.2 Organización de código

- No crear nueva app Django. Usar `apps/ventas` para mesas/cuentas/mesero y `apps/cocina` para mejoras de cocina.
- Nuevos módulos sugeridos:
  - `apps/ventas/mesero_views.py` o vistas en `views.py` con prefijo claro.
  - `apps/ventas/cuentas_services.py` para lógica de cuentas/rondas.
- Plantillas:
  - `templates/base_mesero.html`
  - `templates/mesero/*`
  - `templates/ventas/mesas*.html`
  - `templates/cocina/historial.html`, `agotados.html`
  - `templates/nucleo/pedidos_supervision.html`

### 8.3 Tiempo real: decisión recomendada

Opción recomendada para el MVP: **polling controlado** (cada 10-15 segundos) mediante endpoints JSON ligeros, con recarga parcial de listas.  
Motivos: el stack actual no incluye Channels/Redis; mantiene simplicidad y compatibilidad con MySQL/SQLite; cumple "tecnología equivalente".

Opción futura: Django Channels + Redis para WebSockets verdaderos, solo si el polling no cumple tiempos de respuesta.

Los endpoints de polling deben devolver solo datos mínimos (id, estado, ronda, mesa, tiempo transcurrido) y el frontend debe degradar correctamente si la red falla (la BD sigue siendo la fuente de verdad).

---

## 9. Backlog priorizado

### Épica A — Administración de mesas

- HU: Dueño registra y administra mesas.
- Tareas:
  - Vistas CRUD de mesas (crear, editar, capacidad, activar/desactivar).
  - Validación de número único.
  - Listado con estado derivado (libre/ocupada).
  - Permisos `mesas.*`.
  - Pruebas de validación y permisos.

### Épica B — Panel del mesero

- HU18, HU19, HU20, HU21, HU24.
- Tareas:
  - `base_mesero.html` y menú.
  - Inicio con mesas y pedidos activos.
  - Vista de mesas con estados.
  - Apertura de cuenta con control de concurrencia.
  - Carrito POS reutilizable (productos, cantidades, observaciones).
  - Confirmación de pedido y generación de número.
  - Consulta de estado y notificación de listo.

### Épica C — Rondas y modificaciones

- HU21, HU27.
- Tareas:
  - Lógica de actualización vs. nueva ronda.
  - Numeración de rondas.
  - Actualización de venta agregada.
  - Auditoría de modificaciones.
  - Pruebas de modificación antes/después de preparación.

### Épica D — Cocina avanzada

- HU22, HU23.
- Tareas:
  - Tiempo transcurrido y prioridad en tablero.
  - Historial de cocina.
  - Reporte de productos agotados.
  - Registro de incidencias.
  - Optimización táctil y responsive.

### Épica E — Tiempo real

- HU22, HU24.
- Tareas:
  - Endpoints JSON de polling.
  - Auto-refresco en cocina y mesero.
  - Recuperación tras desconexión.
  - Indicador de última actualización.

### Épica F — Anulaciones

- HU27.
- Tareas:
  - Cancelación de pedido con autorización.
  - Notificación a cocina si está en preparación.
  - Devolución/ajuste de pagos.
  - Auditoría completa.

### Épica G — Supervisión del dueño

- HU26.
- Tareas:
  - Vista de pedidos por estado.
  - Tiempo promedio de preparación.
  - Pedidos por modalidad.
  - Actividad de meseros y cocina.
  - Detalle de pedido.

---

## 10. Criterios de aceptación (Fase 3)

1. Las mesas se pueden registrar y administrar visualmente.
2. Un mesero puede abrir una mesa y registrar pedidos.
3. No se permite abrir la misma mesa como dos cuentas distintas.
4. Los pedidos de salón aparecen en cocina sin recarga manual (o con polling documentado).
5. Se pueden agregar productos a una cuenta existente; si cocina ya comenzó, se crea una nueva ronda identificable.
6. Los cambios de estado se reflejan en los paneles autorizados.
7. Las modificaciones quedan auditadas.
8. Las anulaciones respetan permisos y no eliminan historial.
9. Los estados de pago y preparación son independientes.
10. Se evitan pedidos duplicados.
11. Los pedidos se recuperan tras una desconexión.
12. El dueño puede consultar todas las operaciones.
13. No se duplican ventas al integrar paneles.
14. `manage.py check` y `makemigrations --check` pasan.
15. La suite de pruebas supera el total actual (objetivo: ≥ 110 pruebas).

---

## 11. Riesgos y decisiones pendientes

| Riesgo | Mitigación |
|---|---|
| Complejidad de cuentas agregadas y rondas | Implementar primero el flujo mínimo (una venta por ronda) si el agregado retrasa el sprint; mantener el diseño agregado como objetivo |
| Tiempo real con Channels/Redis | Usar polling como equivalente en el MVP |
| Concurrencia en apertura de mesas | Restricción única parcial en BD + `select_for_update` |
| Migraciones sobre datos existentes | Hacer campos nuevos nullables y migraciones de datos conservadoras |
| Crecimiento de pruebas | Agregar pruebas por épica, no al final |

### Decisiones a confirmar con el usuario

1. ¿Se implementa la venta agregada por cuenta o se mantiene una venta por ronda en el MVP?
2. ¿La administración de mesas vive en `/panel/` (dueño) o también en `/caja/`?
3. ¿El polling se fija en 10 s o 15 s? ¿Se permite configurarlo?
4. ¿Se incluyen productos agotados e incidencias en este sprint o se difieren?
5. ¿Se crea una vista de supervisión de pedidos separada o se amplía el dashboard existente?

---

## 12. Orden de implementación recomendado

1. Permisos y roles (`mesas`, cocina ampliada).
2. Administración visual de mesas + pruebas.
3. Modelo `CuentaMesa` y migraciones.
4. Panel mesero básico (mesas, apertura de cuenta).
5. Registro de pedido de salón desde mesero.
6. Rondas y modificaciones.
7. Mejoras de cocina (tiempo, prioridad, historial).
8. Polling y endpoints JSON.
9. Productos agotados e incidencias.
10. Anulaciones controladas.
11. Supervisión del dueño.
12. Pruebas de integración y documentación.

---

## 13. Estimación de pruebas

| Área | Pruebas nuevas estimadas |
|---|---:|
| Mesas (admin) | 6 |
| Cuentas y concurrencia | 8 |
| Pedidos de salón (mesero) | 8 |
| Rondas y modificaciones | 6 |
| Cocina avanzada | 5 |
| Anulaciones | 4 |
| Supervisión del dueño | 4 |
| Polling/endpoints | 4 |
| **Total nuevas** | **45** |
| **Total acumulado esperado** | **125** |

---

## 14. Siguiente paso

Confirmar este plan y las decisiones pendientes. Una vez confirmado, comenzar por la Épica A (administración de mesas) y la Épica B (panel del mesero), manteniendo compatibilidad con las 80 pruebas actuales y sin tocar el pedido por internet.
