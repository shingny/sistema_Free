"""Reglas de negocio de caja, ventas, pagos y pedidos.

Las vistas validan permisos; este módulo concentra las validaciones de datos y
las operaciones que deben ocurrir dentro de una misma transacción.
"""
import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.nucleo.models import Configuracion
from apps.nucleo.validaciones import validar_nombre, validar_solo_digitos, validar_telefono

from .models import Caja, CuentaMesa, DetallePedido, DetalleVenta, Mesa, MetodoPago, MovimientoCaja, Pago, Pedido, TurnoCaja, Venta

CENTAVO = Decimal("0.01")


def _decimal(valor, campo="monto"):
    try:
        return Decimal(str(valor)).quantize(CENTAVO)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f"El {campo} no es válido.")


def _turno_abierto(usuario):
    return TurnoCaja.objects.filter(usuario=usuario, estado="abierta").select_related("caja").first()


def abrir_caja(usuario, caja, monto_inicial, observacion=""):
    """Abre el turno del usuario. Un usuario y una caja solo pueden tener un turno abierto."""
    monto = _decimal(monto_inicial, "monto inicial")
    if monto < 0:
        raise ValidationError("El monto inicial no puede ser negativo.")
    if not caja.activa:
        raise ValidationError("La caja está inactiva.")
    if TurnoCaja.objects.filter(usuario=usuario, estado="abierta").exists():
        raise ValidationError("Ya tienes un turno de caja abierto.")
    if TurnoCaja.objects.filter(caja=caja, estado="abierta").exists():
        raise ValidationError("La caja ya tiene un turno abierto.")
    with transaction.atomic():
        turno = TurnoCaja.objects.create(
            caja=caja, usuario=usuario, monto_inicial=monto, observacion_apertura=observacion.strip()
        )
        MovimientoCaja.objects.create(
            turno=turno, tipo="apertura", monto=monto, afecta_efectivo=True,
            descripcion="Apertura de caja", creado_por=usuario,
        )
    return turno


def cerrar_caja(turno, usuario, monto_contado, observacion=""):
    """Cierra el turno y conserva el cálculo de efectivo esperado y la diferencia."""
    if turno.estado != "abierta":
        raise ValidationError("Este turno ya está cerrado.")
    contado = _decimal(monto_contado, "efectivo contado")
    if contado < 0:
        raise ValidationError("El efectivo contado no puede ser negativo.")
    esperado = turno.efectivo_calculado()
    with transaction.atomic():
        turno.monto_contado = contado
        turno.efectivo_esperado = esperado
        turno.diferencia = contado - esperado
        turno.observacion_cierre = observacion.strip()
        turno.estado = "cerrada"
        turno.fecha_cierre = timezone.now()
        turno.cerrado_por = usuario
        turno.save(update_fields=[
            "monto_contado", "efectivo_esperado", "diferencia", "observacion_cierre",
            "estado", "fecha_cierre", "cerrado_por",
        ])
    return turno


def registrar_movimiento(turno, usuario, tipo, monto, descripcion, autorizado_por=None):
    """Ingreso o egreso manual de efectivo. El cierre conserva el historial."""
    if turno.estado != "abierta":
        raise ValidationError("No se pueden registrar movimientos en un turno cerrado.")
    if tipo not in ("ingreso", "egreso"):
        raise ValidationError("Tipo de movimiento no válido.")
    monto = _decimal(monto)
    if monto <= 0:
        raise ValidationError("El monto debe ser mayor a cero.")
    if not descripcion.strip():
        raise ValidationError("Describe el motivo del movimiento.")
    return MovimientoCaja.objects.create(
        turno=turno, tipo=tipo, monto=monto, afecta_efectivo=True,
        descripcion=descripcion.strip(), autorizado_por=autorizado_por, creado_por=usuario,
    )


def _movimiento_venta(venta, pago):
    if pago.afecta_efectivo:
        MovimientoCaja.objects.create(
            turno=venta.turno, tipo="venta", monto=pago.monto, afecta_efectivo=True,
            metodo_pago=pago.metodo, venta=venta, pago=pago,
            descripcion=f"Venta {venta.numero} · {pago.metodo.nombre}", creado_por=pago.creado_por,
        )


def _crear_pago(venta, usuario, metodo, monto, referencia="", observacion=""):
    estado = "pendiente_verificacion" if metodo.requiere_verificacion else "verificado"
    pago = Pago.objects.create(
        venta=venta, metodo=metodo, monto=monto, referencia=referencia.strip(),
        observacion=observacion.strip(), estado=estado, creado_por=usuario,
        verificado_por=None if metodo.requiere_verificacion else usuario,
        fecha_verificacion=None if metodo.requiere_verificacion else timezone.now(),
    )
    if pago.estado == "verificado":
        _movimiento_venta(venta, pago)
    return pago


def _detalles_normalizados(items):
    if not items:
        raise ValidationError("Agrega al menos un producto a la venta.")
    cantidades = {}
    observaciones = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("Hay un producto con un formato inválido en el pedido.")
        try:
            producto_id = int(item.get("producto_id"))
            cantidad = int(item.get("cantidad", 1))
        except (TypeError, ValueError):
            raise ValidationError("Hay un producto o una cantidad inválida.")
        if producto_id <= 0:
            raise ValidationError("Hay un producto inválido en el pedido.")
        if cantidad <= 0:
            raise ValidationError("Las cantidades deben ser mayores a cero.")
        if cantidad > 999:
            raise ValidationError("La cantidad máxima por producto es 999.")
        cantidades[producto_id] = cantidades.get(producto_id, 0) + cantidad
        if item.get("observacion"):
            observaciones[producto_id] = str(item["observacion"])[:200]
    productos = {
        p.pk: p for p in Producto.objects.disponibles().select_related("categoria").filter(pk__in=cantidades)
    }
    if len(productos) != len(cantidades):
        raise ValidationError("Uno de los productos ya no está disponible para la venta.")
    detalles = []
    subtotal = Decimal("0.00")
    for producto_id, cantidad in cantidades.items():
        producto = productos[producto_id]
        linea = producto.precio * cantidad
        subtotal += linea
        detalles.append({
            "producto": producto, "cantidad": cantidad, "precio": producto.precio,
            "subtotal": linea, "observacion": observaciones.get(producto_id, ""),
        })
    return detalles, subtotal


@transaction.atomic
def crear_venta(usuario, turno, items, token=None, cliente_nombre="", cliente_documento="",
                cliente_telefono="", observacion="", descuento="0", descuento_motivo="",
                pago_metodo=None, pago_monto="0", pago_referencia="", pago_observacion="",
                origen="para_llevar", mesa=None):
    """Registra una venta, sus detalles, su pedido y el primer pago (si corresponde)."""
    token = token or uuid.uuid4()
    existente = Venta.objects.filter(token=token).select_related("pedido").first()
    if existente:
        return existente, False
    if turno.estado != "abierta":
        raise ValidationError("El turno de caja está cerrado. Abre un turno para vender.")
    if turno.usuario_id != usuario.pk:
        raise ValidationError("Solo puedes vender desde tu propio turno de caja.")
    detalles, subtotal = _detalles_normalizados(items)
    descuento = _decimal(descuento, "descuento")
    if descuento < 0 or descuento > subtotal:
        raise ValidationError("El descuento no puede ser negativo ni mayor al subtotal.")
    if descuento > 0:
        if not usuario.tiene_permiso("ventas", "descuento"):
            raise PermissionError("No tienes permiso para aplicar descuentos.")
        if not descuento_motivo.strip():
            raise ValidationError("Indica el motivo del descuento.")
    total = subtotal - descuento
    if total <= 0:
        raise ValidationError("El total de la venta debe ser mayor a cero.")
    if origen not in ("para_llevar", "salon"):
        raise ValidationError("La modalidad de la venta no es válida.")
    if origen == "salon":
        if mesa is None or not mesa.activa:
            raise ValidationError("Selecciona una mesa activa para el pedido de salón.")
    else:
        mesa = None
    cliente_nombre = validar_nombre(cliente_nombre, "El nombre del cliente") if (cliente_nombre or "").strip() else ""
    cliente_documento = (
        validar_solo_digitos(cliente_documento, "El documento del cliente")
        if (cliente_documento or "").strip() else ""
    )
    cliente_telefono = validar_telefono(cliente_telefono, "El teléfono del cliente")
    monto_pago = Decimal("0.00")
    if pago_metodo is not None:
        if not pago_metodo.activo:
            raise ValidationError("El método de pago seleccionado está inactivo.")
        monto_pago = _decimal(pago_monto, "monto del pago")
        if monto_pago <= 0:
            raise ValidationError("El monto del pago debe ser mayor a cero.")
        if monto_pago > total:
            raise ValidationError("El pago no puede superar el total de la venta.")
        config = Configuracion.obtener()
        if not config.permitir_pago_parcial and monto_pago < total:
            raise ValidationError("El negocio no permite pagos parciales: el pago debe cubrir el total.")
    elif origen != "salon":
        raise ValidationError("Selecciona un método de pago.")

    pedido = Pedido.objects.create(
        origen=origen, mesa=mesa, cliente_nombre=cliente_nombre.strip(),
        cliente_telefono=cliente_telefono.strip(), observacion=observacion.strip(),
        total=total, creado_por=usuario,
    )
    for d in detalles:
        DetallePedido.objects.create(
            pedido=pedido, producto=d["producto"], nombre_producto=d["producto"].nombre,
            precio_unitario=d["precio"], cantidad=d["cantidad"], subtotal=d["subtotal"],
            observacion=d["observacion"],
        )

    venta = Venta.objects.create(
        token=token, turno=turno, cajero=usuario, pedido=pedido,
        cliente_nombre=cliente_nombre.strip(), cliente_documento=cliente_documento.strip(),
        cliente_telefono=cliente_telefono.strip(), subtotal=subtotal, descuento=descuento,
        total=total, observacion=observacion.strip(), descuento_motivo=descuento_motivo.strip(),
        descuento_autorizado_por=usuario if descuento > 0 else None,
    )
    for d in detalles:
        DetalleVenta.objects.create(
            venta=venta, producto=d["producto"], nombre_producto=d["producto"].nombre,
            precio_unitario=d["precio"], cantidad=d["cantidad"], subtotal=d["subtotal"],
            observacion=d["observacion"],
        )
    if pago_metodo is not None:
        _crear_pago(venta, usuario, pago_metodo, monto_pago, pago_referencia, pago_observacion)
    venta.recalcular_estado_pago()
    return venta, True


@transaction.atomic
def registrar_pago(venta, usuario, metodo, monto, referencia="", observacion=""):
    """Agrega un pago a una venta existente (permite completar un pago parcial)."""
    if venta.estado == "anulada":
        raise ValidationError("No se pueden registrar pagos en una venta anulada.")
    if not metodo.activo:
        raise ValidationError("El método de pago seleccionado está inactivo.")
    monto = _decimal(monto)
    if monto <= 0:
        raise ValidationError("El monto del pago debe ser mayor a cero.")
    saldo = venta.saldo_disponible
    if saldo <= 0:
        raise ValidationError(
            "La venta ya tiene el pago completo registrado o hay un pago pendiente de verificación."
        )
    if monto > saldo:
        raise ValidationError("El pago no puede superar el saldo disponible de la venta.")
    config = Configuracion.obtener()
    if not config.permitir_pago_parcial and monto < saldo:
        raise ValidationError("El negocio no permite pagos parciales: el pago debe cubrir el saldo disponible.")
    pago = _crear_pago(venta, usuario, metodo, monto, referencia, observacion)
    venta.recalcular_estado_pago()
    return pago


@transaction.atomic
def verificar_pago(pago, usuario):
    if pago.estado != "pendiente_verificacion":
        raise ValidationError("Este pago no está pendiente de verificación.")
    pago.estado = "verificado"
    pago.verificado_por = usuario
    pago.fecha_verificacion = timezone.now()
    pago.save(update_fields=["estado", "verificado_por", "fecha_verificacion"])
    _movimiento_venta(pago.venta, pago)
    pago.venta.recalcular_estado_pago()
    return pago


@transaction.atomic
def rechazar_pago(pago, usuario):
    if pago.estado != "pendiente_verificacion":
        raise ValidationError("Este pago no está pendiente de verificación.")
    pago.estado = "rechazado"
    pago.verificado_por = usuario
    pago.fecha_verificacion = timezone.now()
    pago.save(update_fields=["estado", "verificado_por", "fecha_verificacion"])
    pago.venta.recalcular_estado_pago()
    return pago


@transaction.atomic
def anular_venta(venta, usuario, motivo):
    if venta.estado == "anulada":
        raise ValidationError("La venta ya está anulada.")
    if not motivo.strip():
        raise ValidationError("Indica el motivo de la anulación.")
    for pago in venta.pagos.select_related("metodo"):
        if pago.estado == "verificado" and pago.afecta_efectivo:
            MovimientoCaja.objects.create(
                turno=venta.turno, tipo="devolucion", monto=pago.monto, afecta_efectivo=True,
                metodo_pago=pago.metodo, venta=venta, pago=pago,
                descripcion=f"Devolución por anulación de {venta.numero}",
                creado_por=usuario,
            )
        if pago.estado in ("verificado", "pendiente_verificacion"):
            pago.estado = "reembolsado"
            pago.save(update_fields=["estado"])
    venta.estado = "anulada"
    venta.anulada_por = usuario
    venta.motivo_anulacion = motivo.strip()
    venta.fecha_anulacion = timezone.now()
    venta.save(update_fields=["estado", "anulada_por", "motivo_anulacion", "fecha_anulacion", "actualizada"])
    if venta.pedido_id:
        venta.pedido.estado = "cancelado"
        venta.pedido.save(update_fields=["estado", "actualizado"])
    if venta.cuenta_id:
        for pedido in venta.cuenta.pedidos.exclude(estado="cancelado"):
            pedido.estado = "cancelado"
            pedido.save(update_fields=["estado", "actualizado"])
        venta.cuenta.estado = "cancelada"
        venta.cuenta.cerrada = timezone.now()
        venta.cuenta.save(update_fields=["estado", "cerrada"])
    venta.recalcular_estado_pago()
    return venta


TRANSICIONES_PEDIDO = {
    "pendiente": {"en_preparacion", "cancelado"},
    "en_preparacion": {"listo", "cancelado"},
    "listo": {"entregado", "cancelado"},
    "entregado": set(),
    "cancelado": set(),
}


def cambiar_estado_pedido(pedido, nuevo_estado):
    if nuevo_estado not in TRANSICIONES_PEDIDO.get(pedido.estado, set()):
        raise ValidationError("Ese cambio de estado no está permitido.")
    pedido.estado = nuevo_estado
    pedido.save(update_fields=["estado", "actualizado"])
    return pedido


def caja_principal():
    return Caja.objects.filter(activa=True).order_by("nombre").first()


def metodos_activos():
    return MetodoPago.objects.filter(activo=True)


# ---------------------------------------------------------------- Cuentas de mesa (salón)
def abrir_cuenta_mesa(usuario, mesa, cliente_nombre="", observacion=""):
    """Abre una cuenta de atención sobre una mesa. Reutiliza la cuenta abierta si existe."""
    mesa = Mesa.objects.filter(pk=mesa.pk).first() if hasattr(mesa, "pk") else Mesa.objects.filter(pk=mesa).first()
    if mesa is None or not mesa.activa:
        raise ValidationError("La mesa seleccionada no está disponible.")
    cliente_nombre = validar_nombre(cliente_nombre, "El nombre del cliente") if (cliente_nombre or "").strip() else ""
    with transaction.atomic():
        mesa = Mesa.objects.select_for_update().get(pk=mesa.pk)
        cuenta = CuentaMesa.objects.filter(
            mesa=mesa, estado__in=["abierta", "cobro_solicitado"]
        ).first()
        if cuenta is not None:
            return cuenta, False
        cuenta = CuentaMesa.objects.create(
            mesa=mesa, mesero=usuario,
            cliente_nombre=(cliente_nombre or "").strip(),
            observacion=(observacion or "").strip(),
        )
    return cuenta, True


def cuenta_abierta_de_mesa(mesa_pk):
    return CuentaMesa.objects.filter(
        mesa_id=mesa_pk, estado__in=["abierta", "cobro_solicitado"]
    ).select_related("mesa", "mesero", "venta").first()


def crear_ronda_pedido(usuario, cuenta, items, observacion="", prioridad="normal"):
    """Crea o actualiza la ronda pendiente de una cuenta de mesa."""
    if cuenta.estado != "abierta":
        raise ValidationError("La cuenta ya no admite nuevos pedidos. Solicita el cobro o libera la mesa.")
    detalles, subtotal = _detalles_normalizados(items)
    if subtotal <= 0:
        raise ValidationError("El total del pedido debe ser mayor a cero.")

    with transaction.atomic():
        cuenta = CuentaMesa.objects.select_for_update().get(pk=cuenta.pk)
        ultimo = cuenta.pedidos.order_by("-ronda", "-creado").first()
        if ultimo is not None and ultimo.estado == "pendiente":
            pedido = ultimo
            pedido.detalles.all().delete()
            es_nueva_ronda = False
        else:
            max_ronda = cuenta.pedidos.aggregate(maximo=Max("ronda"))["maximo"] or 0
            pedido = Pedido(
                cuenta=cuenta, mesa=cuenta.mesa, origen="salon",
                creado_por=usuario, ronda=max_ronda + 1,
            )
            es_nueva_ronda = True

        pedido.cliente_nombre = cuenta.cliente_nombre
        pedido.observacion = (observacion or pedido.observacion or "").strip()
        pedido.prioridad = prioridad if prioridad in dict(Pedido.PRIORIDADES) else "normal"
        pedido.total = subtotal
        pedido.save()

        for d in detalles:
            DetallePedido.objects.create(
                pedido=pedido, producto=d["producto"],
                nombre_producto=d["producto"].nombre,
                precio_unitario=d["precio"], cantidad=d["cantidad"],
                subtotal=d["subtotal"], observacion=d["observacion"],
            )

    # Si la cuenta ya tiene una venta agregada (cobro iniciado), se actualiza.
    try:
        venta = cuenta.venta
    except Venta.DoesNotExist:
        venta = None
    if venta is not None:
        pedidos = list(cuenta.pedidos.exclude(estado="cancelado"))
        subtotal = sum((p.total for p in pedidos), Decimal("0.00"))
        venta.detalles.all().delete()
        for pedido in pedidos:
            for det in pedido.detalles.all():
                DetalleVenta.objects.create(
                    venta=venta, producto=det.producto,
                    nombre_producto=det.nombre_producto,
                    precio_unitario=det.precio_unitario,
                    cantidad=det.cantidad, subtotal=det.subtotal,
                    observacion=det.observacion,
                )
        venta.subtotal = subtotal
        venta.total = subtotal
        venta.save(update_fields=["subtotal", "total", "actualizada"])
        venta.recalcular_estado_pago()

    return pedido, es_nueva_ronda


def solicitar_cobro_cuenta(cuenta, usuario):
    if cuenta.estado == "cancelada":
        raise ValidationError("No se puede solicitar cobro de una cuenta cancelada.")
    if cuenta.estado == "cerrada":
        raise ValidationError("La cuenta ya está cerrada.")
    if cuenta.estado == "cobro_solicitado":
        raise ValidationError("El cobro de esta cuenta ya fue solicitado.")
    if not cuenta.pedidos.exclude(estado="cancelado").exists():
        raise ValidationError("La cuenta no tiene consumos. Agrega productos antes de solicitar el cobro.")
    cuenta.estado = "cobro_solicitado"
    cuenta.save(update_fields=["estado"])
    return cuenta


def obtener_o_crear_venta_cuenta(usuario, turno, cuenta):
    """Obtiene o crea la venta agregada de una cuenta, usando el turno del cajero."""
    if turno is None or turno.estado != "abierta":
        raise ValidationError("Abre un turno de caja para cobrar la cuenta.")
    if turno.usuario_id != usuario.pk:
        raise ValidationError("Solo puedes cobrar desde tu propio turno de caja.")
    with transaction.atomic():
        cuenta = CuentaMesa.objects.select_for_update().select_related("venta").get(pk=cuenta.pk)
        try:
            venta_existente = cuenta.venta
        except Venta.DoesNotExist:
            venta_existente = None
        if venta_existente is not None:
            return venta_existente, False
        pedidos = list(cuenta.pedidos.exclude(estado="cancelado"))
        if not pedidos:
            raise ValidationError("La cuenta no tiene pedidos para cobrar.")
        subtotal = sum((p.total for p in pedidos), Decimal("0.00"))
        if subtotal <= 0:
            raise ValidationError("El total de la cuenta debe ser mayor a cero.")
        venta = Venta.objects.create(
            turno=turno, cajero=usuario, cuenta=cuenta,
            cliente_nombre=cuenta.cliente_nombre,
            subtotal=subtotal, descuento=Decimal("0.00"), total=subtotal,
            observacion=cuenta.observacion,
        )
        for pedido in pedidos:
            for det in pedido.detalles.all():
                DetalleVenta.objects.create(
                    venta=venta, producto=det.producto,
                    nombre_producto=det.nombre_producto,
                    precio_unitario=det.precio_unitario,
                    cantidad=det.cantidad, subtotal=det.subtotal,
                    observacion=det.observacion,
                )
        venta.recalcular_estado_pago()
    return venta, True


def cerrar_cuenta_mesa(cuenta, usuario):
    if cuenta.pedidos.exclude(estado__in=["entregado", "cancelado"]).exists():
        raise ValidationError("No se puede cerrar la cuenta mientras haya pedidos pendientes o en preparación.")
    tiene_consumos = cuenta.pedidos.exclude(estado="cancelado").exists()
    try:
        venta_cuenta = cuenta.venta
    except Venta.DoesNotExist:
        venta_cuenta = None
    if tiene_consumos:
        if venta_cuenta is None:
            raise ValidationError("La cuenta tiene consumos sin cobrar. Caja debe registrar el pago antes de cerrarla.")
        if venta_cuenta.estado != "anulada" and venta_cuenta.estado_pago not in ("pagado", "reembolsado"):
            raise ValidationError("No se puede cerrar la cuenta hasta que el pago esté completo.")
    cuenta.estado = "cerrada"
    cuenta.cerrada = timezone.now()
    cuenta.save(update_fields=["estado", "cerrada"])
    return cuenta


@transaction.atomic
def cancelar_ronda_pedido(pedido, usuario, motivo, autorizado=False):
    """Cancela una ronda de salón y ajusta la venta agregada si no tiene pagos."""
    if pedido.estado == "cancelado":
        raise ValidationError("El pedido ya está cancelado.")
    if pedido.estado not in ("pendiente", "en_preparacion", "listo"):
        raise ValidationError("No se puede cancelar un pedido en este estado.")
    if pedido.estado != "pendiente" and not autorizado:
        raise ValidationError("Se requiere autorización para cancelar un pedido en preparación o listo.")
    if not (motivo or "").strip():
        raise ValidationError("Indica el motivo de la cancelación.")
    cuenta = pedido.cuenta
    pedido.estado = "cancelado"
    pedido.save(update_fields=["estado", "actualizado"])

    try:
        venta = cuenta.venta if cuenta is not None else None
    except Venta.DoesNotExist:
        venta = None

    if cuenta is not None and venta is not None and venta.estado != "anulada":
        if venta.pagos.filter(estado__in=["verificado", "pendiente_verificacion"]).exists():
            raise ValidationError("La cuenta ya tiene pagos; anula la venta completa para cancelar la ronda.")
        pedidos_activos = list(cuenta.pedidos.exclude(estado="cancelado"))
        if not pedidos_activos:
            anular_venta(venta, usuario, motivo.strip())
        else:
            subtotal = sum((p.total for p in pedidos_activos), Decimal("0.00"))
            venta.detalles.all().delete()
            for p in pedidos_activos:
                for det in p.detalles.all():
                    DetalleVenta.objects.create(
                        venta=venta, producto=det.producto,
                        nombre_producto=det.nombre_producto,
                        precio_unitario=det.precio_unitario,
                        cantidad=det.cantidad, subtotal=det.subtotal,
                        observacion=det.observacion,
                    )
            venta.subtotal = subtotal
            venta.total = subtotal
            venta.save(update_fields=["subtotal", "total", "actualizada"])
            venta.recalcular_estado_pago()
    return pedido
