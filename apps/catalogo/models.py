import uuid

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


def ruta_imagen_producto(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"productos/{uuid.uuid4().hex}.{extension}"


class Categoria(models.Model):
    nombre = models.CharField("Nombre", max_length=60, unique=True)
    descripcion = models.CharField("Descripción", max_length=200, blank=True)
    orden = models.PositiveSmallIntegerField("Orden de aparición", default=0)
    activo = models.BooleanField("Activa", default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class ProductoQuerySet(models.QuerySet):
    def disponibles(self):
        """Productos que pueden venderse: activos y de una categoría activa.
        Los módulos de venta (Sprint 2 en adelante) deben usar siempre este filtro."""
        return self.filter(activo=True, categoria__activo=True)


class Producto(models.Model):
    nombre = models.CharField("Nombre", max_length=100)
    descripcion = models.TextField("Descripción", blank=True, max_length=500)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos",
                                  verbose_name="Categoría")
    precio = models.DecimalField("Precio de venta (S/)", max_digits=8, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"), "El precio debe ser mayor a cero.")])
    imagen = models.ImageField("Imagen", upload_to=ruta_imagen_producto, blank=True)
    activo = models.BooleanField("Activo", default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    objects = ProductoQuerySet.as_manager()

    class Meta:
        ordering = ["categoria__orden", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["categoria", "nombre"], name="producto_unico_por_categoria"),
        ]

    def __str__(self):
        return self.nombre
