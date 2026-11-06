from django.contrib.auth.backends import ModelBackend

from .models import Usuario


class UsuarioBackend(ModelBackend):
    """Carga el usuario junto con su rol.

    AuthenticationMiddleware pide el usuario en cada petición; al traer el rol en
    la misma consulta se elimina un viaje de red por panel (clave con base remota).
    """

    def get_user(self, user_id):
        try:
            user = Usuario.objects.select_related("rol").get(pk=user_id)
        except Usuario.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
