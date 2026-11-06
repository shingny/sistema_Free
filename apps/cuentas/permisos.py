"""Catálogo de permisos (módulo + acción) y control de acceso en el backend."""
from functools import wraps

from django.shortcuts import render

# Cada módulo declara solo las acciones que realmente existen en el sistema.
CATALOGO_PERMISOS = {
    "dashboard": ["ver"],
    "usuarios": ["ver", "crear", "editar", "desactivar", "autorizar"],
    "roles": ["ver", "editar"],
    "productos": ["ver", "crear", "editar", "desactivar", "reportes"],
    "categorias": ["ver", "crear", "editar", "desactivar"],
    "configuracion": ["ver", "editar"],
    "auditoria": ["ver", "reportes"],
    "ventas": ["ver", "crear", "anular", "descuento", "reportes"],
    "pagos": ["ver", "registrar", "verificar", "reembolsar"],
    "caja": ["ver", "abrir", "mover", "cerrar", "supervisar"],
    "pedidos": ["ver", "editar", "cancelar", "autorizar_cancelacion"],
    "cocina": ["ver", "actualizar", "reportar_agotado", "registrar_incidencia", "ver_historial"],
    "mesas": ["ver", "gestionar", "abrir", "cerrar"],
    "metodos_pago": ["ver", "crear", "editar", "desactivar"],
}

# Permisos base de cada rol (los que se asignan al inicializar el sistema).
# El dueño siempre tiene todos y por eso no se lista aquí.
PERMISOS_INICIALES = {
    "administrador": [
        "dashboard.ver", "usuarios.ver", "usuarios.crear", "usuarios.editar", "usuarios.desactivar",
        "roles.ver", "roles.editar",
        "productos.ver", "productos.crear", "productos.editar", "productos.desactivar", "productos.reportes",
        "categorias.ver", "categorias.crear", "categorias.editar", "categorias.desactivar",
        "configuracion.ver",
        "auditoria.ver", "auditoria.reportes",
        "ventas.ver", "ventas.crear", "ventas.anular", "ventas.descuento", "ventas.reportes",
        "pagos.ver", "pagos.registrar", "pagos.verificar", "pagos.reembolsar",
        "caja.ver", "caja.abrir", "caja.mover", "caja.cerrar", "caja.supervisar",
        "pedidos.ver", "pedidos.editar", "pedidos.cancelar", "pedidos.autorizar_cancelacion",
        "cocina.ver", "cocina.actualizar", "cocina.reportar_agotado", "cocina.registrar_incidencia", "cocina.ver_historial",
        "mesas.ver", "mesas.gestionar", "mesas.abrir", "mesas.cerrar",
        "metodos_pago.ver", "metodos_pago.crear", "metodos_pago.editar", "metodos_pago.desactivar",
    ],
    "jefe_cocina": [
        "productos.ver", "categorias.ver", "pedidos.ver",
        "cocina.ver", "cocina.actualizar", "cocina.reportar_agotado", "cocina.registrar_incidencia", "cocina.ver_historial",
        "mesas.ver",
    ],
    "cajero": [
        "productos.ver", "categorias.ver",
        "ventas.ver", "ventas.crear",
        "pagos.ver", "pagos.registrar",
        "caja.ver", "caja.abrir", "caja.mover", "caja.cerrar",
        "pedidos.ver", "pedidos.editar",
        "mesas.ver",
    ],
    "mesero": [
        "productos.ver", "categorias.ver",
        "pedidos.ver", "pedidos.editar", "pedidos.cancelar",
        "mesas.ver", "mesas.abrir", "mesas.cerrar",
        "cocina.ver",
    ],
    "cocinero": [
        "productos.ver", "categorias.ver", "pedidos.ver",
        "cocina.ver", "cocina.actualizar", "cocina.reportar_agotado", "cocina.registrar_incidencia", "cocina.ver_historial",
    ],
}

# Permisos que se muestran al administrar cada rol. El dueño y el administrador
# pueden recibir cualquier permiso; los roles operativos solo los de su función,
# para no llenar la pantalla con opciones que nunca van a usar.
PERMISOS_POR_ROL = {
    **PERMISOS_INICIALES,
    "dueno": None,
    "administrador": None,
}


def permisos_visibles(codigo_rol):
    """Permisos visibles para un rol. Devuelve None cuando ve el catálogo completo."""
    return PERMISOS_POR_ROL.get(codigo_rol)


NOMBRES_MODULO = {
    "dashboard": "Dashboard",
    "usuarios": "Usuarios",
    "roles": "Roles y permisos",
    "productos": "Productos",
    "categorias": "Categorías",
    "configuracion": "Configuración",
    "auditoria": "Actividad (auditoría)",
    "ventas": "Ventas",
    "pagos": "Pagos",
    "caja": "Caja",
    "pedidos": "Pedidos",
    "cocina": "Cocina",
    "mesas": "Mesas",
    "metodos_pago": "Métodos de pago",
}

NOMBRES_ACCION = {
    "ver": "Ver",
    "crear": "Crear",
    "editar": "Editar",
    "desactivar": "Desactivar",
    "autorizar": "Autorizar",
    "reportes": "Reportes",
    "anular": "Anular",
    "descuento": "Aplicar descuentos",
    "registrar": "Registrar",
    "verificar": "Verificar",
    "reembolsar": "Reembolsar",
    "abrir": "Abrir",
    "mover": "Registrar movimientos",
    "cerrar": "Cerrar",
    "supervisar": "Supervisar",
    "cancelar": "Cancelar",
    "autorizar_cancelacion": "Autorizar cancelación",
    "actualizar": "Actualizar estado",
    "reportar_agotado": "Reportar producto agotado",
    "registrar_incidencia": "Registrar incidencia",
    "ver_historial": "Ver historial",
    "gestionar": "Gestionar",
    "abrir": "Abrir",
    "cerrar": "Cerrar",
}

AYUDA_ACCION = {
    ("usuarios", "autorizar"): "Restablecer contraseñas",
    ("roles", "editar"): "Cambiar los permisos de un rol",
    ("productos", "reportes"): "Exportar productos a CSV",
    ("auditoria", "reportes"): "Exportar actividad a CSV",
    ("ventas", "crear"): "Registrar ventas en el POS",
    ("ventas", "anular"): "Anular ventas con motivo",
    ("ventas", "descuento"): "Aplicar descuentos autorizados",
    ("ventas", "reportes"): "Consultar ventas de todos los cajeros",
    ("pagos", "verificar"): "Verificar transferencias y pagos electrónicos",
    ("pagos", "reembolsar"): "Reembolsar pagos de ventas anuladas",
    ("caja", "supervisar"): "Ver todas las cajas y turnos",
    ("metodos_pago", "editar"): "Configurar los medios de pago",
    ("cocina", "actualizar"): "Avanzar pedidos en cocina",
}


def todos_los_permisos():
    return [(m, a) for m, acciones in CATALOGO_PERMISOS.items() for a in acciones]


def denegar(request, modulo, accion):
    """Responde 403 y deja constancia del intento."""
    from apps.nucleo.auditoria import registrar

    registrar(request, "acceso_denegado", modulo,
              descripcion=f"Intento de «{accion}» sin permiso en {modulo} ({request.method} {request.path})")
    return render(request, "403.html", status=403)


def permiso_requerido(modulo, accion):
    """Decorador de vistas: la validación real ocurre aquí, no en el frontend."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.is_authenticated:
                # Import local: evita cargar auth.views antes de que el registro
                # de apps termine de inicializar el modelo Usuario.
                from django.contrib.auth.views import redirect_to_login

                return redirect_to_login(request.get_full_path())
            if not request.user.tiene_permiso(modulo, accion):
                return denegar(request, modulo, accion)
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
