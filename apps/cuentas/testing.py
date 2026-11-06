"""Utilidades compartidas por las pruebas de todas las apps."""
from django.core.management import call_command

from apps.cuentas.models import Rol, Usuario

CLAVE = "Clave-Segura-2026"


def preparar_roles():
    call_command("inicializar", verbosity=0)


def crear_usuario(username, rol_codigo, **extra):
    usuario = Usuario(username=username, first_name=username.capitalize(), last_name="Prueba",
                      rol=Rol.objects.get(codigo=rol_codigo), **extra)
    usuario.set_password(CLAVE)
    usuario.save()
    return usuario
