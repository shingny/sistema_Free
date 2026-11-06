# Sprint 1 — Panel administrativo del dueño

## 1. Objetivo
Entregar el centro de administración del sistema: acceso seguro, personal, roles y permisos, carta de productos
(categorías, precios), configuración del negocio y supervisión de la actividad.

## 2. Arquitectura
Una sola aplicación Django con tres apps sobre una única base MySQL:

| App | Responsabilidad |
|---|---|
| `cuentas` | Usuario personalizado, roles, permisos, inicio de sesión, perfil, gestión de usuarios y de roles |
| `catalogo` | Categorías y productos |
| `nucleo` | Configuración del negocio, auditoría, dashboard, menú y utilidades comunes |

- **Autenticación:** Argon2, sesión de 8 h con expiración por inactividad, bloqueo de 15 min tras 5 intentos fallidos,
  contraseña temporal de un solo uso para altas y restablecimientos (obliga a cambiarla), cierre de sesiones al desactivar o restablecer.
- **Autorización (RBAC):** `Permiso (módulo, acción)` ↔ `Rol`. Cada vista se protege con `@permiso_requerido(módulo, acción)`;
  el backend responde 403 y registra el intento. Ocultar botones es solo comodidad visual.
- **Jerarquía:** cada rol tiene un nivel (Dueño 100, Administrador 80, Jefe de cocina 50, Cajero/Mesero 30, Cocinero 20).
  Nadie gestiona usuarios ni edita roles de nivel igual o superior; nadie concede permisos que no posee; solo el dueño asigna el rol Dueño;
  el rol Dueño no se edita; siempre debe quedar un dueño activo.
- **Auditoría:** tabla `Auditoria` inalterable (guardar/borrar/actualizar lanzan error), con usuario, fecha/hora (America/Lima),
  acción, entidad, valores antes/después e IP. Se escribe en la misma transacción que la operación (`ATOMIC_REQUESTS`). Nunca guarda contraseñas.
- **Regionalización:** español, PEN, `America/Lima`.

## 3. Modelo de datos
- `Permiso(modulo, accion)` único.  `Rol(codigo, nombre, descripcion, nivel, permisos M2M)`.
- `Usuario` (extiende `AbstractUser`): nombres (`first_name`), apellidos (`last_name`), `documento` único opcional, `username`, `email` opcional,
  `telefono` opcional, `rol`, estado (`is_active`), fecha de registro (`date_joined`), `debe_cambiar_password`, `intentos_fallidos`, `bloqueado_hasta`, `creado_por`.
- `Categoria(nombre único, descripcion, orden, activo, creado, actualizado)`.
- `Producto(nombre, descripcion, categoria, precio Decimal(8,2) > 0, imagen opcional, activo, creado, actualizado)`; único por (categoría, nombre).
  `Producto.objects.disponibles()` devuelve solo productos activos de categorías activas: **los módulos de venta deben usar siempre este filtro**.
- `Configuracion` (registro único): nombre comercial, razón social, RUC, dirección, teléfono, correo, horario, logo, moneda, zona horaria.
- `Auditoria(fecha, usuario, usuario_nombre, accion, modulo, entidad, entidad_id, descripcion, antes, despues, ip)`.

## 4. Permisos definidos (módulo → acciones)
dashboard: ver · usuarios: ver, crear, editar, desactivar, autorizar (restablecer contraseña) · roles: ver, editar ·
productos: ver, crear, editar, desactivar, reportes (CSV) · categorías: ver, crear, editar, desactivar ·
configuración: ver, editar · auditoría: ver, reportes (CSV).
Se definen solo las acciones que hacen algo hoy; los Sprints 2 y 3 añadirán módulos con `python manage.py inicializar` (idempotente, no toca permisos ya configurados).

## 5. Product Backlog y Sprint Backlog
| HU | Historia | Entregado en |
|---|---|---|
| HU01 | Iniciar sesión | `/ingresar/`, bloqueo, sesión, contraseña temporal |
| HU02 | Registrar trabajadores | `/usuarios/nuevo/`, edición, búsqueda y filtros |
| HU03 | Asignar roles | Formulario de usuario con restricción por nivel |
| HU04 | Gestionar permisos | `/roles/<id>/permisos/` (matriz módulo × acción) |
| HU05 | Registrar productos | `/productos/nuevo/` con imagen opcional |
| HU06 | Organizar categorías | `/categorias/` |
| HU07 | Actualizar precios | Edición de producto; cambio auditado con antes/después |
| HU08 | Desactivar productos | Botón con confirmación; `disponibles()` los excluye |
| HU09 | Consultar actividad | Dashboard y `/actividad/` con filtros y exportación CSV |

## 6. Interfaz
Menú lateral (Dashboard, Usuarios, Roles y permisos, Productos, Categorías, Configuración, Mi perfil, Cerrar sesión) filtrado por permisos,
barra superior con perfil, indicadores, tablas con búsqueda/filtros/paginación, formularios con validación en cliente y servidor,
ventanas de confirmación, notificaciones, diseño adaptable a celular y tableta. El dashboard solo muestra datos reales;
Ventas, Pedidos e Inventario aparecen como espacios reservados rotulados, sin cifras.

## 7. Criterios de aceptación → pruebas
Archivos `apps/*/tests.py` (≈45 pruebas): inicio de sesión y bloqueo, 403 en backend, jerarquía de roles, permisos delegables,
contraseñas con hash y temporales, cierre de sesión al desactivar, precios exactos y auditados, productos inactivos fuera de `disponibles()`,
auditoría inalterable, persistencia de configuración y exportaciones restringidas.

## 8. Decisiones y límites documentados
- No se crean roles nuevos desde la interfaz (solo los seis iniciales); se pueden configurar sus permisos.
- No se elimina ningún registro: todo se desactiva.
- Moneda y zona horaria se muestran fijas (reglas del proyecto).
- La actividad se consulta desde el dashboard y desde cada usuario; no tiene entrada propia en el menú para respetar el menú definido.
- Las imágenes reemplazadas quedan en `media/` (no se borran automáticamente).
- Los roles Cajero, Mesero, Cocinero y Jefe de cocina solo tienen lectura de productos y categorías; sus paneles llegan en los Sprints 2 y 3.

## 9. Pendiente / siguiente
- **Ejecución real de las pruebas y generación de migraciones**: este entorno no tenía Django ni acceso a internet, por lo que el código se revisó
  y compiló, pero las pruebas y la aplicación **no se ejecutaron aún**. Ejecuta los pasos del README y corrige lo que aparezca antes de aprobar el Sprint.
- Copias de seguridad automáticas (script `mysqldump` y programación en el servidor).
- Sprint 2 (caja y ventas) solo debe iniciar cuando el Sprint 1 esté verificado.
