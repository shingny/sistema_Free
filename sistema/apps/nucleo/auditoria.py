"""Utilidades para registrar la auditoría. Nunca se guardan contraseñas."""
from django.conf import settings
from django.db.models.fields.files import FieldFile

from .models import Auditoria

ETIQUETAS_ACCION = {
    "crear": "Creación",
    "editar": "Edición",
    "activar": "Activación",
    "desactivar": "Desactivación",
    "cambio_precio": "Cambio de precio",
    "permisos": "Cambio de permisos",
    "restablecer_password": "Restablecimiento de contraseña",
    "cambiar_password": "Cambio de contraseña",
    "login": "Inicio de sesión",
    "logout": "Cierre de sesión",
    "login_fallido": "Inicio de sesión fallido",
    "bloqueo": "Cuenta bloqueada",
    "acceso_denegado": "Acceso denegado",
    "exportar": "Exportación",
    "venta": "Registro de venta",
    "descuento": "Descuento autorizado",
    "anular": "Anulación",
    "pago": "Registro de pago",
    "verificar_pago": "Verificación de pago",
    "rechazar_pago": "Rechazo de pago",
    "abrir_caja": "Apertura de caja",
    "movimiento_caja": "Movimiento de caja",
    "cerrar_caja": "Cierre de caja",
    "pedido_estado": "Cambio de estado de pedido",
}


def ip_cliente(request):
    if request is None:
        return None
    if settings.USAR_X_FORWARDED_FOR:
        reenviado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if reenviado:
            return reenviado.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def valores(objeto, campos):
    """Instantánea serializable de los campos indicados."""
    datos = {}
    for campo in campos:
        valor = getattr(objeto, campo, None)
        if isinstance(valor, FieldFile):
            valor = valor.name or ""
        elif hasattr(valor, "pk"):
            valor = str(valor)
        datos[campo] = valor
    return datos


def cambios(antes, despues):
    """Devuelve solo los campos que cambiaron: (antes, despues)."""
    a, d = {}, {}
    for clave in despues:
        if antes.get(clave) != despues.get(clave):
            a[clave] = antes.get(clave)
            d[clave] = despues.get(clave)
    return a, d


def registrar(request, accion, modulo, objeto=None, descripcion="", antes=None, despues=None,
              usuario=None, usuario_nombre=""):
    if usuario is None and request is not None:
        candidato = getattr(request, "user", None)
        if candidato is not None and candidato.is_authenticated:
            usuario = candidato
    nombre = usuario_nombre or (usuario.get_username() if usuario else "")
    return Auditoria.objects.create(
        usuario=usuario,
        usuario_nombre=nombre[:150],
        accion=accion,
        modulo=modulo,
        entidad=objeto.__class__.__name__ if objeto is not None else "",
        entidad_id=str(objeto.pk) if objeto is not None and objeto.pk else "",
        descripcion=descripcion[:255],
        antes=antes,
        despues=despues,
        ip=ip_cliente(request),
    )
