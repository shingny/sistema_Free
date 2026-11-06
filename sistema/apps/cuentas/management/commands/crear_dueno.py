import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.cuentas.models import Rol, Usuario

from .inicializar import inicializar_roles_y_permisos


class Command(BaseCommand):
    help = "Crea la cuenta del dueño. La contraseña se pide por consola (o variable DUENO_PASSWORD)."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True)
        parser.add_argument("--nombres", required=True)
        parser.add_argument("--apellidos", required=True)

    def handle(self, *args, **opts):
        inicializar_roles_y_permisos()
        if Usuario.objects.filter(username__iexact=opts["usuario"]).exists():
            raise CommandError("Ese nombre de usuario ya existe.")
        clave = os.environ.get("DUENO_PASSWORD") or getpass.getpass("Contraseña: ")
        if not os.environ.get("DUENO_PASSWORD") and clave != getpass.getpass("Repite la contraseña: "):
            raise CommandError("Las contraseñas no coinciden.")
        usuario = Usuario(
            username=opts["usuario"].lower(), first_name=opts["nombres"], last_name=opts["apellidos"],
            rol=Rol.objects.get(codigo="dueno"),
        )
        try:
            validate_password(clave, usuario)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages))
        usuario.set_password(clave)
        usuario.save()
        self.stdout.write(self.style.SUCCESS(f"Dueño «{usuario.username}» creado."))
