import secrets

from django.contrib.sessions.models import Session
from django.db.models import Q
from django.utils import timezone

from .models import Rol, Usuario

_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generar_password_temporal(longitud=12):
    while True:
        clave = "".join(secrets.choice(_ALFABETO) for _ in range(longitud))
        if any(c.islower() for c in clave) and any(c.isupper() for c in clave) and any(c.isdigit() for c in clave):
            return clave


def roles_asignables(actor):
    """El dueño asigna cualquier rol; los demás solo roles de nivel inferior al suyo."""
    if actor.es_dueno:
        return Rol.objects.all()
    return Rol.objects.filter(nivel__lt=actor.nivel)


def puede_gestionar(actor, objetivo):
    """Un usuario nunca se gestiona a sí mismo aquí (usa Mi perfil) ni a quien tiene igual o mayor nivel."""
    if actor.pk == objetivo.pk:
        return False
    if actor.es_dueno:
        return True
    return objetivo.nivel < actor.nivel


def cerrar_sesiones(usuario):
    for sesion in Session.objects.filter(expire_date__gte=timezone.now()):
        if str(sesion.get_decoded().get("_auth_user_id")) == str(usuario.pk):
            sesion.delete()


def quedan_duenos_activos(excluyendo):
    return (
        Usuario.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(rol__codigo="dueno"))
        .exclude(pk=excluyendo.pk)
        .exists()
    )
