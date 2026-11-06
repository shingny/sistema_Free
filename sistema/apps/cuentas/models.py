from django.contrib.auth.models import AbstractUser
from django.core.cache import cache
from django.db import models

from .permisos import CATALOGO_PERMISOS, NOMBRES_ACCION, NOMBRES_MODULO, todos_los_permisos


class Permiso(models.Model):
    modulo = models.CharField(max_length=30, choices=[(k, v) for k, v in NOMBRES_MODULO.items()])
    accion = models.CharField(max_length=30, choices=[(k, v) for k, v in NOMBRES_ACCION.items()])

    class Meta:
        unique_together = [("modulo", "accion")]
        ordering = ["modulo", "accion"]

    def __str__(self):
        return f"{self.modulo}.{self.accion}"

    @property
    def clave(self):
        return f"{self.modulo}.{self.accion}"


class Rol(models.Model):
    """El nivel jerárquico limita a quién puede administrar cada usuario."""

    codigo = models.SlugField(max_length=30, unique=True)
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    nivel = models.PositiveSmallIntegerField()
    permisos = models.ManyToManyField(Permiso, blank=True, related_name="roles")

    class Meta:
        verbose_name = "rol"
        verbose_name_plural = "roles"
        ordering = ["-nivel", "nombre"]

    def __str__(self):
        return self.nombre

    @property
    def es_dueno(self):
        return self.codigo == "dueno"

    def claves_permisos(self):
        if self.es_dueno:  # el dueño siempre conserva todos los permisos
            return {f"{m}.{a}" for m, a in todos_los_permisos()}
        clave_cache = f"cuentas.rol_permisos.{self.pk}"
        claves = cache.get(clave_cache)
        if claves is None:
            claves = {p.clave for p in self.permisos.all()}
            cache.set(clave_cache, claves, 300)
        return claves


class Usuario(AbstractUser):
    """first_name = nombres, last_name = apellidos, is_active = estado, date_joined = fecha de registro."""

    documento = models.CharField("Documento de identidad", max_length=12, unique=True, null=True, blank=True)
    telefono = models.CharField("Teléfono", max_length=20, blank=True)
    rol = models.ForeignKey(Rol, null=True, blank=True, on_delete=models.PROTECT, related_name="usuarios")
    debe_cambiar_password = models.BooleanField(default=False)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["first_name", "last_name"]

    @property
    def nombre_completo(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

    @property
    def es_dueno(self):
        return self.is_superuser or (self.rol_id is not None and self.rol.es_dueno)

    @property
    def nivel(self):
        if self.is_superuser:
            return 1000
        return self.rol.nivel if self.rol_id else 0

    def permisos_set(self):
        """Conjunto de claves 'modulo.accion'. Se calcula una vez por instancia (por petición)."""
        if not self.is_active:
            return set()
        if not hasattr(self, "_permisos_cache"):
            if self.is_superuser:
                self._permisos_cache = {f"{m}.{a}" for m, a in todos_los_permisos()}
            elif self.rol_id:
                self._permisos_cache = self.rol.claves_permisos()
            else:
                self._permisos_cache = set()
        return self._permisos_cache

    def tiene_permiso(self, modulo, accion):
        return f"{modulo}.{accion}" in self.permisos_set()
