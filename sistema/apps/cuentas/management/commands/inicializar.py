from django.core.management.base import BaseCommand

from apps.cuentas.models import Permiso, Rol
from apps.cuentas.permisos import PERMISOS_INICIALES, todos_los_permisos

ROLES = [
    ("dueno", "Dueño", 100, "Control total del sistema y supervisión de todas las operaciones."),
    ("administrador", "Administrador", 80, "Administra el sistema según los permisos que le otorgue el dueño."),
    ("jefe_cocina", "Jefe de cocina", 50, "Coordina la cocina y supervisa la preparación."),
    ("cajero", "Cajero", 30, "Registra pedidos para llevar, cobros y gestiona su caja."),
    ("mesero", "Mesero", 30, "Atiende mesas y registra pedidos de salón."),
    ("cocinero", "Cocinero", 20, "Prepara los pedidos y actualiza su estado."),
]

# Los permisos base por rol viven en apps/cuentas/permisos.py (PERMISOS_INICIALES).
# Reglas de negocio aplicadas:
#   - Administrador/Dueño: acceso total a todos los módulos.
#   - Cajero: cobrar y gestionar su caja; consultar productos pero NO modificar precios, productos ni inventario.
#   - Mesero: crear/editar/enviar pedidos, administrar mesas, consultar productos; NO cobrar, NO modificar precios, NO ver información financiera.
#   - Cocinero: preparar pedidos, registrar agotados y solicitudes de reposición; NO caja, NO cobros, NO reportes financieros, NO modificar pedidos de meseros (solo su preparación).
#   - Anulaciones/cancelaciones: requieren autorización del administrador (pedidos.autorizar_cancelacion solo en administrador).
# Se agregan a los roles existentes solo si faltan; nunca se quitan permisos.


def inicializar_roles_y_permisos():
    """Idempotente. Agrega los permisos base que falten, sin quitar los que el dueño haya dado."""
    for modulo, accion in todos_los_permisos():
        Permiso.objects.get_or_create(modulo=modulo, accion=accion)
    creados = []
    for codigo, nombre, nivel, descripcion in ROLES:
        rol, nuevo = Rol.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre, "nivel": nivel, "descripcion": descripcion}
        )
        if nuevo:
            creados.append(nombre)
        for clave in PERMISOS_INICIALES.get(codigo, []):
            modulo, accion = clave.split(".")
            permiso = Permiso.objects.get(modulo=modulo, accion=accion)
            if not rol.permisos.filter(pk=permiso.pk).exists():
                rol.permisos.add(permiso)
    return creados


class Command(BaseCommand):
    help = "Crea los permisos y los roles iniciales (puede ejecutarse varias veces sin riesgo)."

    def handle(self, *args, **options):
        creados = inicializar_roles_y_permisos()
        if creados:
            self.stdout.write(self.style.SUCCESS("Roles creados: " + ", ".join(creados)))
        else:
            self.stdout.write("Roles y permisos al día.")
