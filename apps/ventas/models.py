import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from apps.catalogo.models import Producto


class Caja(models.Model):
    """Caja física o lógica donde se cobra. En el MVP existe una sola: Caja principal."""

    nombre = models.CharField("Nombre", max_length=60, unique=True)
    codigo = models.CharField("Código", max_length=20, unique=True)
    activa = models.BooleanField("Activa", default=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "caja"
        verbose_name_plural = "cajas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class MetodoPago(models.Model):
    """Medio de pago configurable. Los electrónicos pueden exigir verificación."""

    codigo = models.SlugField("Código", max_length=30, unique=True)
    nombre = models.CharField("Nombre", max_length=60, unique=True)
    afecta_efectivo = models.BooleanField("Afecta el efectivo físico", default=False)
    requiere_verificacion = models.BooleanField("Requiere verificación", default=False)
    activo = models.BooleanField("Activo", default=True)
    orden = models.PositiveSmallIntegerField("Orden", default=0)

    class Meta:
        verbose_name = "método de pago"
        verbose_name_plural = "métodos de pago"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return self.nombre


class TurnoCaja(models.Model):
    """Sesión de trabajo de un cajero sobre una caja."""

    ESTADOS = [("abierta", "Abierta"), ("cerrada", "Cerrada")]

    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name="turnos", verbose_name="Caja")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos_caja", verbose_name="Cajero"
    )
    estado = models.CharField("Estado", max_length=10, choices=ESTADOS, default="abierta")
    fecha_apertura = models.DateTimeField("Fecha de apertura", auto_now_add=True)
    monto_inicial = models.DecimalField(
        "Monto inicial (S/)", max_digits=10, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    observacion_apertura = models.CharField("Observación de apertura", max_length=200, blank=True)
    fecha_cierre = models.DateTimeField("Fecha de cierre", null=True, blank=True)
    monto_contado = models.DecimalField(
        "Efectivo contado (S/)", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    efectivo_esperado = models.DecimalField(
        "Efectivo esperado (S/)", max_digits=10, decimal_places=2, null=True, blank=True
    )
    diferencia = models.DecimalField("Diferencia (S/)", max_digits=10, decimal_places=2, null=True, blank=True)
    observacion_cierre = models.CharField("Observación de cierre", max_length=300, blank=True)
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "turno de caja"
        verbose_name_plural = "turnos de caja"
        ordering = ["-fecha_apertura"]
        constraints = [
            models.UniqueConstraint(
                fields=["caja"], condition=Q(estado="abierta"), name="turno_abierto_por_caja"
            ),
            models.UniqueConstraint(
                fields=["usuario"], condition=Q(estado="abierta"), name="turno_abierto_por_usuario"
            ),
        ]

    def __str__(self):
        return f"{self.caja} · {self.usuario} · {self.fecha_apertura:%d/%m/%Y %H:%M}"

    @property
    def esta_abierta(self):
        return self.estado == "abierta"

    def efectivo_calculado(self):
        """Monto inicial + ingresos de ventas/manuales - egresos - devoluciones (solo efectivo)."""
        movimientos = self.movimientos.filter(afecta_efectivo=True)
        ingresos = movimientos.filter(tipo__in=["venta", "ingreso"]).aggregate(
            total=Sum("monto")
        )["total"] or Decimal("0.00")
        salidas = movimientos.filter(tipo__in=["egreso", "devolucion"]).aggregate(
            total=Sum("monto")
        )["total"] or Decimal("0.00")
        return self.monto_inicial + ingresos - salidas


class Mesa(models.Model):
    """Mesa física del salón."""

    numero = models.PositiveSmallIntegerField("Número", unique=True)
    nombre = models.CharField("Nombre", max_length=40, blank=True)
    capacidad = models.PositiveSmallIntegerField("Capacidad", default=4)
    activa = models.BooleanField("Activa", default=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "mesa"
        verbose_name_plural = "mesas"
        ordering = ["numero"]

    def __str__(self):
        return self.nombre or f"Mesa {self.numero}"


class CuentaMesa(models.Model):
    """Cuenta de atención abierta sobre una mesa (agrupa rondas de pedido)."""

    ESTADOS = [
        ("abierta", "Abierta"),
        ("cobro_solicitado", "Cobro solicitado"),
        ("cerrada", "Cerrada"),
        ("cancelada", "Cancelada"),
    ]

    mesa = models.ForeignKey(
        "Mesa", on_delete=models.PROTECT, related_name="cuentas", verbose_name="Mesa"
    )
    mesero = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="cuentas_abiertas", verbose_name="Mesero",
    )
    estado = models.CharField("Estado", max_length=20, choices=ESTADOS, default="abierta")
    cliente_nombre = models.CharField("Cliente", max_length=120, blank=True)
    observacion = models.CharField("Observación", max_length=300, blank=True)
    abierta = models.DateTimeField("Abierta", auto_now_add=True)
    cerrada = models.DateTimeField("Cerrada", null=True, blank=True)

    class Meta:
        verbose_name = "cuenta de mesa"
        verbose_name_plural = "cuentas de mesa"
        ordering = ["-abierta"]
        constraints = [
            models.UniqueConstraint(
                fields=["mesa"], condition=Q(estado__in=["abierta", "cobro_solicitado"]),
                name="cuenta_abierta_por_mesa",
            ),
        ]

    def __str__(self):
        return f"{self.mesa} · {self.get_estado_display()}"

    @property
    def esta_abierta(self):
        return self.estado in ("abierta", "cobro_solicitado")


class IncidenciaCocina(models.Model):
    """Producto agotado o incidencia registrada por cocina."""

    TIPOS = [("producto_agotado", "Producto agotado"), ("incidencia", "Incidencia")]
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("en_camino", "En camino"),
        ("rechazado", "Rechazado"),
        ("resuelto", "Resuelto"),
    ]

    pedido = models.ForeignKey(
        "Pedido", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="incidencias", verbose_name="Pedido",
    )
    producto = models.ForeignKey(
        "catalogo.Producto", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name="Producto",
    )
    tipo = models.CharField("Tipo", max_length=25, choices=TIPOS, default="incidencia")
    estado = models.CharField("Estado", max_length=15, choices=ESTADOS, default="pendiente")
    descripcion = models.CharField("Descripción", max_length=300)
    observacion_dueno = models.CharField("Observación del dueño", max_length=300, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="incidencias_cocina"
    )
    creado = models.DateTimeField("Creado", auto_now_add=True)

    class Meta:
        verbose_name = "incidencia de cocina"
        verbose_name_plural = "incidencias de cocina"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.descripcion[:40]}"


class Pedido(models.Model):
    """Pedido operativo. En Sprint 2 se genera desde una venta para llevar."""

    ORIGENES = [("para_llevar", "Para llevar"), ("salon", "Salón")]
    ESTADOS = [
        ("pendiente", "Pendiente"),
        ("en_preparacion", "En preparación"),
        ("listo", "Listo"),
        ("entregado", "Entregado"),
        ("cancelado", "Cancelado"),
    ]
    PRIORIDADES = [("normal", "Normal"), ("alta", "Alta"), ("urgente", "Urgente")]

    numero = models.CharField("Número", max_length=20, unique=True, null=True, blank=True)
    cuenta = models.ForeignKey(
        "CuentaMesa", null=True, blank=True, on_delete=models.PROTECT,
        related_name="pedidos", verbose_name="Cuenta de mesa",
    )
    mesa = models.ForeignKey(
        "Mesa", null=True, blank=True, on_delete=models.PROTECT,
        related_name="pedidos", verbose_name="Mesa",
    )
    ronda = models.PositiveSmallIntegerField("Ronda", default=1)
    prioridad = models.CharField("Prioridad", max_length=10, choices=PRIORIDADES, default="normal")
    origen = models.CharField("Origen", max_length=15, choices=ORIGENES, default="para_llevar")
    estado = models.CharField("Estado", max_length=20, choices=ESTADOS, default="pendiente")
    cliente_nombre = models.CharField("Cliente", max_length=120, blank=True)
    cliente_telefono = models.CharField("Teléfono del cliente", max_length=20, blank=True)
    observacion = models.CharField("Observación", max_length=300, blank=True)
    total = models.DecimalField("Total (S/)", max_digits=10, decimal_places=2, default=Decimal("0.00"))
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos_creados"
    )
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-creado"]

    def __str__(self):
        return self.numero or f"Pedido #{self.pk}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = f"TMP-{uuid.uuid4().hex[:12]}"
        super().save(*args, **kwargs)
        if self.numero.startswith("TMP-"):
            self.numero = f"P-{timezone.localdate(self.creado):%Y%m%d}-{self.pk:06d}"
            super().save(update_fields=["numero"])


class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="+")
    nombre_producto = models.CharField("Producto", max_length=100)
    precio_unitario = models.DecimalField("Precio unitario (S/)", max_digits=8, decimal_places=2)
    cantidad = models.PositiveIntegerField("Cantidad", validators=[MinValueValidator(1)])
    subtotal = models.DecimalField("Subtotal (S/)", max_digits=10, decimal_places=2)
    observacion = models.CharField("Observación", max_length=200, blank=True)

    class Meta:
        verbose_name = "detalle de pedido"
        verbose_name_plural = "detalles de pedido"

    def __str__(self):
        return f"{self.cantidad} × {self.nombre_producto}"


class Venta(models.Model):
    """Venta cerrada. Conserva precios y nombres históricos de los productos."""

    ESTADOS_PAGO = [
        ("pendiente", "Pendiente"),
        ("parcial", "Parcial"),
        ("pagado", "Pagado"),
        ("reembolsado", "Reembolsado"),
    ]
    ESTADOS = [("registrada", "Registrada"), ("anulada", "Anulada")]

    numero = models.CharField("Número", max_length=20, unique=True, null=True, blank=True)
    token = models.UUIDField("Token de idempotencia", unique=True, default=uuid.uuid4, editable=False)
    turno = models.ForeignKey(TurnoCaja, on_delete=models.PROTECT, related_name="ventas")
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ventas_realizadas"
    )
    pedido = models.OneToOneField(
        Pedido, null=True, blank=True, on_delete=models.PROTECT, related_name="venta"
    )
    cuenta = models.OneToOneField(
        "CuentaMesa", null=True, blank=True, on_delete=models.PROTECT,
        related_name="venta", verbose_name="Cuenta de mesa",
    )
    cliente_nombre = models.CharField("Cliente", max_length=120, blank=True)
    cliente_documento = models.CharField("Documento del cliente", max_length=20, blank=True)
    cliente_telefono = models.CharField("Teléfono del cliente", max_length=20, blank=True)
    subtotal = models.DecimalField("Subtotal (S/)", max_digits=10, decimal_places=2)
    descuento = models.DecimalField("Descuento (S/)", max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField("Total (S/)", max_digits=10, decimal_places=2)
    estado_pago = models.CharField("Estado del pago", max_length=15, choices=ESTADOS_PAGO, default="pendiente")
    estado = models.CharField("Estado de la venta", max_length=12, choices=ESTADOS, default="registrada")
    observacion = models.CharField("Observación", max_length=300, blank=True)
    descuento_motivo = models.CharField("Motivo del descuento", max_length=200, blank=True)
    descuento_autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    motivo_anulacion = models.CharField("Motivo de anulación", max_length=300, blank=True)
    fecha_anulacion = models.DateTimeField(null=True, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        ordering = ["-creada"]

    def __str__(self):
        return self.numero or f"Venta #{self.pk}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = f"TMP-{uuid.uuid4().hex[:12]}"
        super().save(*args, **kwargs)
        if self.numero.startswith("TMP-"):
            self.numero = f"V-{timezone.localdate(self.creada):%Y%m%d}-{self.pk:06d}"
            super().save(update_fields=["numero"])

    @property
    def total_pagado(self):
        return self.pagos.filter(estado="verificado").aggregate(total=Sum("monto"))["total"] or Decimal("0.00")

    @property
    def total_en_verificacion(self):
        return self.pagos.filter(estado="pendiente_verificacion").aggregate(
            total=Sum("monto")
        )["total"] or Decimal("0.00")

    @property
    def saldo_pendiente(self):
        return max(self.total - self.total_pagado, Decimal("0.00"))

    @property
    def saldo_disponible(self):
        """Saldo que aún puede recibir un pago nuevo, descontando pagos por verificar."""
        return max(self.total - self.total_pagado - self.total_en_verificacion, Decimal("0.00"))

    @property
    def esta_anulada(self):
        return self.estado == "anulada"

    def recalcular_estado_pago(self):
        if self.estado == "anulada":
            self.estado_pago = "reembolsado"
        else:
            pagado = self.total_pagado
            if pagado >= self.total:
                self.estado_pago = "pagado"
            elif pagado > 0:
                self.estado_pago = "parcial"
            else:
                self.estado_pago = "pendiente"
        self.save(update_fields=["estado_pago", "actualizada"])


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="+")
    nombre_producto = models.CharField("Producto", max_length=100)
    precio_unitario = models.DecimalField("Precio unitario (S/)", max_digits=8, decimal_places=2)
    cantidad = models.PositiveIntegerField("Cantidad", validators=[MinValueValidator(1)])
    subtotal = models.DecimalField("Subtotal (S/)", max_digits=10, decimal_places=2)
    observacion = models.CharField("Observación", max_length=200, blank=True)

    class Meta:
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"

    def __str__(self):
        return f"{self.cantidad} × {self.nombre_producto}"


class Pago(models.Model):
    ESTADOS = [
        ("pendiente_verificacion", "Pendiente de verificación"),
        ("verificado", "Verificado"),
        ("rechazado", "Rechazado"),
        ("reembolsado", "Reembolsado"),
    ]

    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="pagos")
    metodo = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name="pagos")
    monto = models.DecimalField(
        "Monto (S/)", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    referencia = models.CharField("Referencia", max_length=100, blank=True)
    estado = models.CharField("Estado", max_length=25, choices=ESTADOS, default="verificado")
    observacion = models.CharField("Observación", max_length=200, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pagos_registrados"
    )
    creado = models.DateTimeField(auto_now_add=True)
    verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    fecha_verificacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        ordering = ["creado"]

    def __str__(self):
        return f"{self.metodo} · S/ {self.monto:.2f}"

    @property
    def afecta_efectivo(self):
        return self.metodo.afecta_efectivo


class MovimientoCaja(models.Model):
    TIPOS = [
        ("apertura", "Apertura"),
        ("venta", "Venta en efectivo"),
        ("ingreso", "Ingreso"),
        ("egreso", "Egreso"),
        ("devolucion", "Devolución"),
    ]

    turno = models.ForeignKey(TurnoCaja, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField("Tipo", max_length=12, choices=TIPOS)
    monto = models.DecimalField(
        "Monto (S/)", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    afecta_efectivo = models.BooleanField("Afecta el efectivo físico", default=True)
    metodo_pago = models.ForeignKey(
        MetodoPago, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos"
    )
    venta = models.ForeignKey(
        Venta, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos_caja"
    )
    pago = models.ForeignKey(
        Pago, null=True, blank=True, on_delete=models.PROTECT, related_name="movimientos_caja"
    )
    descripcion = models.CharField("Descripción", max_length=200)
    autorizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos_creados"
    )
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimiento de caja"
        verbose_name_plural = "movimientos de caja"
        ordering = ["creado", "id"]

    def __str__(self):
        return f"{self.get_tipo_display()} · S/ {self.monto:.2f}"
