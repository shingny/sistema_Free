import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import RegexValidator
from django.db import models


def ruta_logo(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    return f"logo/{uuid.uuid4().hex}.{extension}"


class Configuracion(models.Model):
    """Datos generales de la pollería. Existe un único registro (pk=1)."""

    MONEDAS = [("PEN", "Sol peruano (PEN)")]
    ZONAS = [("America/Lima", "Lima, Perú (America/Lima)")]

    nombre_comercial = models.CharField("Nombre comercial", max_length=120, default="Mi pollería")
    razon_social = models.CharField("Razón social", max_length=150, blank=True)
    ruc = models.CharField(
        "RUC", max_length=11, blank=True,
        validators=[RegexValidator(r"^\d{11}$", "El RUC debe tener 11 dígitos.")],
    )
    direccion = models.CharField("Dirección", max_length=200, blank=True)
    telefono = models.CharField("Teléfono", max_length=20, blank=True)
    correo = models.EmailField("Correo del establecimiento", blank=True)
    horario_atencion = models.CharField("Horario de atención", max_length=150, blank=True)
    logo = models.ImageField("Logo", upload_to=ruta_logo, blank=True)
    moneda = models.CharField("Moneda", max_length=3, choices=MONEDAS, default="PEN")
    zona_horaria = models.CharField("Zona horaria", max_length=40, choices=ZONAS, default="America/Lima")
    permitir_pago_parcial = models.BooleanField("Permitir pago parcial", default=True)
    actualizado = models.DateTimeField(auto_now=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "configuración"
        verbose_name_plural = "configuración"

    def __str__(self):
        return self.nombre_comercial

    @classmethod
    def obtener(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def campos_pendientes(self):
        """Datos básicos que aún no se han registrado."""
        pendientes = []
        for campo in ("direccion", "telefono"):
            if not getattr(self, campo):
                pendientes.append(self._meta.get_field(campo).verbose_name)
        if not self.logo:
            pendientes.append("Logo")
        return pendientes


class AuditoriaQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("El registro de auditoría es inalterable.")

    def delete(self):
        raise PermissionError("El registro de auditoría es inalterable.")


class Auditoria(models.Model):
    """Registro inalterable de las operaciones importantes del sistema."""

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    usuario_nombre = models.CharField(max_length=150, blank=True)
    accion = models.CharField(max_length=40, db_index=True)
    modulo = models.CharField(max_length=30, db_index=True)
    entidad = models.CharField(max_length=60, blank=True)
    entidad_id = models.CharField(max_length=40, blank=True)
    descripcion = models.CharField(max_length=255, blank=True)
    antes = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    despues = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    ip = models.GenericIPAddressField(null=True, blank=True)

    objects = AuditoriaQuerySet.as_manager()

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "auditoría"
        ordering = ["-fecha", "-id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("El registro de auditoría es inalterable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("El registro de auditoría es inalterable.")
