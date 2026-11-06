import json
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalogo.models import Categoria, Producto
from apps.cuentas.models import Usuario
from apps.cuentas.permisos import denegar, permiso_requerido
from apps.nucleo.auditoria import registrar
from apps.nucleo.utils import paginar

from . import services
from .models import CuentaMesa
from .forms import (
    AnulacionForm, AperturaCajaForm, CierreCajaForm, MetodoPagoForm, MovimientoCajaForm, PagoForm,
)
from .models import Mesa, MetodoPago, MovimientoCaja, Pago, Pedido, TurnoCaja, Venta


def _turno_abierto(usuario):
    return TurnoCaja.objects.filter(usuario=usuario, estado="abierta").select_related("caja").first()


def _puede_ver_todo(usuario):
    return usuario.tiene_permiso("ventas", "reportes") or usuario.tiene_permiso("caja", "supervisar")


def _venta_visible(request, pk):
    venta = get_object_or_404(
        Venta.objects.select_related("cajero", "turno", "pedido").prefetch_related(
            "detalles__producto", "pagos__metodo"
        ),
        pk=pk,
    )
    if not _puede_ver_todo(request.user) and venta.cajero_id != request.user.pk:
        return None, denegar(request, "ventas", "ver")
    return venta, None


def _rango_fechas(request, qs, campo="creada"):
    """Aplica desde/hasta (fechas locales) a un queryset."""
    for clave, es_desde in (("desde", True), ("hasta", False)):
        try:
            dia = datetime.strptime(request.GET.get(clave, ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        inicio = timezone.make_aware(datetime.combine(dia, time.min))
        if es_desde:
            qs = qs.filter(**{f"{campo}__gte": inicio})
        else:
            qs = qs.filter(**{f"{campo}__lt": inicio + timedelta(days=1)})
    return qs


def _ns(request):
    """Namespace activo para redirigir dentro del panel correcto."""
    return request.resolver_match.namespace or "ventas"


@permiso_requerido("ventas", "ver")
def inicio(request):
    turno = _turno_abierto(request.user)
    hoy = timezone.localdate()
    ventas_hoy = Venta.objects.filter(cajero=request.user, creada__date=hoy, estado="registrada")
    pedidos_abiertos = Pedido.objects.filter(
        estado__in=["pendiente", "en_preparacion", "listo"]
    ).order_by("creado")[:6]
    contexto = {
        "turno": turno,
        "ventas_hoy": ventas_hoy,
        "total_hoy": ventas_hoy.aggregate(total=Sum("total"))["total"] or Decimal("0.00"),
        "operaciones_hoy": ventas_hoy.count(),
        "pedidos_abiertos": pedidos_abiertos,
        "puede_crear": request.user.tiene_permiso("ventas", "crear"),
    }
    return render(request, "ventas/inicio.html", contexto)


@permiso_requerido("ventas", "crear")
def nueva_venta(request):
    turno = _turno_abierto(request.user)
    if turno is None:
        messages.warning(request, "Primero abre tu turno de caja para comenzar a vender.")
        return redirect(f"{reverse('ventas:caja_abrir')}?next=nueva_venta")

    categorias = Categoria.objects.filter(activo=True).prefetch_related(
        Prefetch("productos", queryset=Producto.objects.disponibles(), to_attr="disponibles")
    ).order_by("orden", "nombre")
    metodos = MetodoPago.objects.filter(activo=True)
    contexto = {
        "turno": turno,
        "categorias": categorias,
        "metodos": metodos,
        "mesas": Mesa.objects.filter(activa=True).order_by("numero"),
        "token": uuid.uuid4(),
        "puede_descontar": request.user.tiene_permiso("ventas", "descuento"),
        "items_json": "[]",
        "pago_form": PagoForm(),
    }

    if request.method == "POST":
        try:
            items = json.loads(request.POST.get("items", "[]"))
            if not isinstance(items, list):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            messages.error(request, "No se pudo leer el carrito. Intenta nuevamente.")
            contexto["items_json"] = request.POST.get("items", "[]")
            return render(request, "ventas/pos.html", contexto)

        origen = request.POST.get("origen", "para_llevar")
        if origen not in ("para_llevar", "salon"):
            origen = "para_llevar"
        mesa = None
        if origen == "salon":
            try:
                mesa = Mesa.objects.get(pk=request.POST.get("mesa"), activa=True)
            except (Mesa.DoesNotExist, ValueError, TypeError):
                messages.error(request, "Selecciona una mesa activa para el pedido de salón.")
                contexto["items_json"] = request.POST.get("items", "[]")
                return render(request, "ventas/pos.html", contexto)

        cobrar_ahora = origen == "para_llevar" or request.POST.get("cobrar_ahora") == "1"
        if cobrar_ahora:
            pago_form = PagoForm(request.POST)
            if not pago_form.is_valid():
                messages.error(request, "Revisa los datos del pago.")
                contexto.update({"pago_form": pago_form, "items_json": request.POST.get("items", "[]")})
                return render(request, "ventas/pos.html", contexto)
            pago_metodo = pago_form.cleaned_data["metodo"]
            pago_monto = pago_form.cleaned_data["monto"]
            pago_referencia = pago_form.cleaned_data.get("referencia", "")
            pago_observacion = pago_form.cleaned_data.get("observacion", "")
        else:
            pago_metodo = None
            pago_monto = "0"
            pago_referencia = ""
            pago_observacion = ""

        try:
            token = uuid.UUID(request.POST.get("token", ""))
        except (ValueError, AttributeError):
            token = uuid.uuid4()

        try:
            venta, creada = services.crear_venta(
                request.user, turno, items, token=token,
                cliente_nombre=request.POST.get("cliente_nombre", ""),
                cliente_documento=request.POST.get("cliente_documento", ""),
                cliente_telefono=request.POST.get("cliente_telefono", ""),
                observacion=request.POST.get("observacion", ""),
                descuento=request.POST.get("descuento", "0") or "0",
                descuento_motivo=request.POST.get("descuento_motivo", ""),
                pago_metodo=pago_metodo,
                pago_monto=pago_monto,
                pago_referencia=pago_referencia,
                pago_observacion=pago_observacion,
                origen=origen,
                mesa=mesa,
            )
        except PermissionError as exc:
            messages.error(request, str(exc))
            contexto["items_json"] = request.POST.get("items", "[]")
            return render(request, "ventas/pos.html", contexto)
        except ValidationError as exc:
            for mensaje in exc.messages:
                messages.error(request, mensaje)
            contexto["items_json"] = request.POST.get("items", "[]")
            return render(request, "ventas/pos.html", contexto)

        if creada:
            registrar(request, "venta", "ventas", venta, f"Registró la venta {venta.numero}")
            if venta.descuento > 0:
                registrar(
                    request, "descuento", "ventas", venta,
                    f"Descuento de S/ {venta.descuento:.2f} en la venta {venta.numero}: "
                    f"{venta.descuento_motivo}",
                )
            messages.success(request, f"Venta {venta.numero} registrada correctamente.")
        else:
            messages.info(request, f"La venta {venta.numero} ya estaba registrada.")
        return redirect(f"{_ns(request)}:venta_ticket", pk=venta.pk)

    return render(request, "ventas/pos.html", contexto)


@permiso_requerido("ventas", "ver")
def historial(request):
    qs = Venta.objects.select_related("cajero", "turno", "pedido").prefetch_related("pagos__metodo")
    if not _puede_ver_todo(request.user):
        qs = qs.filter(cajero=request.user)
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    metodo = request.GET.get("metodo", "")
    usuario = request.GET.get("usuario", "")
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(cliente_nombre__icontains=q) | Q(cliente_documento__icontains=q))
    if estado:
        qs = qs.filter(estado_pago=estado)
    if metodo.isdigit():
        qs = qs.filter(pagos__metodo_id=int(metodo)).distinct()
    if usuario.isdigit() and _puede_ver_todo(request.user):
        qs = qs.filter(cajero_id=int(usuario))
    qs = _rango_fechas(request, qs)
    pagina, parametros = paginar(request, qs, 20)
    contexto = {
        "pagina": pagina,
        "qs": parametros,
        "f": request.GET,
        "metodos": MetodoPago.objects.all(),
        "usuarios": Usuario.objects.filter(ventas_realizadas__isnull=False).distinct().order_by("first_name") if _puede_ver_todo(request.user) else Usuario.objects.none(),
        "estados": Venta.ESTADOS_PAGO,
        "puede_ver_todo": _puede_ver_todo(request.user),
    }
    return render(request, "ventas/historial.html", contexto)


@permiso_requerido("ventas", "ver")
def venta_detalle(request, pk):
    venta, respuesta = _venta_visible(request, pk)
    if respuesta:
        return respuesta
    pago_form = PagoForm(initial={"monto": venta.saldo_disponible})
    contexto = {
        "venta": venta,
        "pago_form": pago_form,
        "saldo": venta.saldo_pendiente,
        "saldo_disponible": venta.saldo_disponible,
        "puede_pagar": (
            request.user.tiene_permiso("pagos", "registrar")
            and venta.estado == "registrada"
            and venta.saldo_disponible > 0
        ),
        "puede_verificar": request.user.tiene_permiso("pagos", "verificar"),
        "puede_anular": request.user.tiene_permiso("ventas", "anular") and venta.estado == "registrada",
        "anulacion_form": AnulacionForm(),
        "movimientos": venta.movimientos_caja.select_related("metodo_pago").order_by("creado"),
    }
    return render(request, "ventas/venta_detalle.html", contexto)


@permiso_requerido("ventas", "ver")
def venta_ticket(request, pk):
    venta, respuesta = _venta_visible(request, pk)
    if respuesta:
        return respuesta
    return render(request, "ventas/ticket.html", {"venta": venta, "saldo": venta.saldo_pendiente})


@require_POST
@permiso_requerido("pagos", "registrar")
def venta_pago(request, pk):
    venta, respuesta = _venta_visible(request, pk)
    if respuesta:
        return respuesta
    form = PagoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa los datos del pago.")
        return redirect(f"{_ns(request)}:venta_detalle", pk=venta.pk)
    try:
        pago = services.registrar_pago(
            venta, request.user, form.cleaned_data["metodo"], form.cleaned_data["monto"],
            form.cleaned_data.get("referencia", ""), form.cleaned_data.get("observacion", ""),
        )
    except ValidationError as exc:
        for mensaje in exc.messages:
            messages.error(request, mensaje)
        return redirect(f"{_ns(request)}:venta_detalle", pk=venta.pk)
    registrar(request, "pago", "pagos", pago,
              f"Registró un pago de S/ {pago.monto:.2f} en la venta {venta.numero}")
    # Si la venta pertenece a una cuenta de mesa y quedó pagada, cerrar la cuenta y liberar la mesa.
    if venta.cuenta_id:
        venta.refresh_from_db()
        if venta.estado_pago == "pagado":
            try:
                services.cerrar_cuenta_mesa(venta.cuenta, request.user)
                messages.success(request, f"Mesa {venta.cuenta.mesa} liberada.")
            except ValidationError:
                pass
    if pago.estado == "pendiente_verificacion":
        messages.warning(request, "Pago registrado. Queda pendiente de verificación por el dueño o un administrador.")
    else:
        messages.success(request, "Pago registrado.")
    return redirect(f"{_ns(request)}:venta_detalle", pk=venta.pk)


@require_POST
@permiso_requerido("pagos", "verificar")
def pago_verificar(request, pk):
    pago = get_object_or_404(Pago.objects.select_related("venta", "metodo"), pk=pk)
    try:
        services.verificar_pago(pago, request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        registrar(request, "verificar_pago", "pagos", pago,
                  f"Verificó el pago {pago.metodo.nombre} de la venta {pago.venta.numero}")
        messages.success(request, "Pago verificado.")
    return redirect(f"{_ns(request)}:venta_detalle", pk=pago.venta_id)


@require_POST
@permiso_requerido("pagos", "verificar")
def pago_rechazar(request, pk):
    pago = get_object_or_404(Pago.objects.select_related("venta", "metodo"), pk=pk)
    try:
        services.rechazar_pago(pago, request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        registrar(request, "rechazar_pago", "pagos", pago,
                  f"Rechazó el pago {pago.metodo.nombre} de la venta {pago.venta.numero}")
        messages.success(request, "Pago rechazado. La venta mantiene su saldo pendiente.")
    return redirect(f"{_ns(request)}:venta_detalle", pk=pago.venta_id)


@require_POST
@permiso_requerido("ventas", "anular")
def venta_anular(request, pk):
    venta, respuesta = _venta_visible(request, pk)
    if respuesta:
        return respuesta
    form = AnulacionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Indica el motivo de la anulación.")
        return redirect(f"{_ns(request)}:venta_detalle", pk=venta.pk)
    try:
        services.anular_venta(venta, request.user, form.cleaned_data["motivo"])
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        registrar(request, "anular", "ventas", venta,
                  f"Anuló la venta {venta.numero}: {venta.motivo_anulacion}")
        messages.success(request, "Venta anulada. El movimiento quedó registrado en auditoría.")
    return redirect(f"{_ns(request)}:venta_detalle", pk=venta.pk)


@permiso_requerido("pedidos", "ver")
def pedidos(request):
    qs = Pedido.objects.select_related("creado_por", "venta", "mesa").prefetch_related("detalles")
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    origen = request.GET.get("origen", "")
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(cliente_nombre__icontains=q))
    if estado:
        qs = qs.filter(estado=estado)
    if origen:
        qs = qs.filter(origen=origen)
    pagina, parametros = paginar(request, qs, 20)
    return render(request, "ventas/pedidos.html", {
        "pagina": pagina, "qs": parametros, "f": request.GET,
        "estados": Pedido.ESTADOS, "origenes": Pedido.ORIGENES,
    })


@permiso_requerido("pedidos", "ver")
def pedido_detalle(request, pk):
    pedido = get_object_or_404(
        Pedido.objects.select_related("creado_por", "mesa").prefetch_related("detalles"), pk=pk
    )
    venta = Venta.objects.filter(pedido=pedido).first()
    siguientes = services.TRANSICIONES_PEDIDO.get(pedido.estado, set())
    return render(request, "ventas/pedido_detalle.html", {
        "pedido": pedido,
        "venta": venta,
        "siguientes": siguientes,
        "puede_editar": request.user.tiene_permiso("pedidos", "editar"),
        "puede_cancelar": request.user.tiene_permiso("pedidos", "cancelar"),
        "puede_anular": request.user.tiene_permiso("ventas", "anular"),
    })


@require_POST
@permiso_requerido("pedidos", "editar")
def pedido_estado(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    nuevo = request.POST.get("estado", "")
    if nuevo == "cancelado":
        if not request.user.tiene_permiso("pedidos", "cancelar"):
            return denegar(request, "pedidos", "cancelar")
        venta = Venta.objects.filter(pedido=pedido).first()
        # Pedido de salón (cuenta agregada): se cancela la ronda y se ajusta la venta.
        if pedido.cuenta_id and not venta:
            if not request.user.tiene_permiso("pedidos", "cancelar"):
                return denegar(request, "pedidos", "cancelar")
            if pedido.estado != "pendiente" and not request.user.tiene_permiso("pedidos", "autorizar_cancelacion"):
                return denegar(request, "pedidos", "autorizar_cancelacion")
            estado_anterior = pedido.estado
            motivo = request.POST.get("motivo", "").strip() or "Cancelación del pedido"
            try:
                services.cancelar_ronda_pedido(pedido, request.user, motivo, autorizado=True)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect(f"{_ns(request)}:pedido_detalle", pk=pedido.pk)
            if estado_anterior in ("en_preparacion", "listo"):
                from apps.ventas.models import IncidenciaCocina
                IncidenciaCocina.objects.create(
                    pedido=pedido, tipo="incidencia",
                    descripcion=f"Cancelación de ronda {pedido.ronda} notificada a cocina: {motivo}",
                    creado_por=request.user,
                )
            registrar(request, "cancelar", "pedidos", pedido,
                      f"Canceló la ronda {pedido.ronda} del pedido {pedido.numero}")
        elif venta and venta.estado != "anulada":
            if not request.user.tiene_permiso("ventas", "anular"):
                return denegar(request, "ventas", "anular")
            motivo = request.POST.get("motivo", "").strip() or "Cancelación del pedido"
            try:
                services.anular_venta(venta, request.user, motivo)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect(f"{_ns(request)}:pedido_detalle", pk=pedido.pk)
            registrar(request, "anular", "pedidos", pedido,
                      f"Canceló el pedido {pedido.numero} y anuló la venta {venta.numero}")
        else:
            if pedido.estado != "pendiente" and not request.user.tiene_permiso("pedidos", "autorizar_cancelacion"):
                return denegar(request, "pedidos", "autorizar_cancelacion")
            services.cambiar_estado_pedido(pedido, "cancelado")
            registrar(request, "pedido_estado", "pedidos", pedido, f"Canceló el pedido {pedido.numero}")
    else:
        try:
            services.cambiar_estado_pedido(pedido, nuevo)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect(f"{_ns(request)}:pedido_detalle", pk=pedido.pk)
        registrar(request, "pedido_estado", "pedidos", pedido,
                  f"Cambió el pedido {pedido.numero} a {pedido.get_estado_display()}")
    messages.success(request, "Pedido actualizado.")
    return redirect(f"{_ns(request)}:pedido_detalle", pk=pedido.pk)


@permiso_requerido("caja", "abrir")
def caja_abrir(request):
    turno = _turno_abierto(request.user)
    form = AperturaCajaForm(request.POST or None, initial={"caja": services.caja_principal()})
    if request.method == "POST" and turno is None:
        if form.is_valid():
            try:
                turno = services.abrir_caja(
                    request.user, form.cleaned_data["caja"], form.cleaned_data["monto_inicial"],
                    form.cleaned_data.get("observacion", ""),
                )
            except ValidationError as exc:
                for mensaje in exc.messages:
                    messages.error(request, mensaje)
            else:
                registrar(request, "abrir_caja", "caja", turno,
                          f"Abrió la caja {turno.caja.nombre} con S/ {turno.monto_inicial:.2f}")
                messages.success(request, "Turno de caja abierto.")
                if request.GET.get("next") == "nueva_venta":
                    return redirect(f"{_ns(request)}:nueva_venta")
                return redirect(f"{_ns(request)}:caja_movimientos")
        else:
            messages.error(request, "Revisa los datos de apertura.")
    return render(request, "ventas/caja_abrir.html", {"form": form, "turno": turno})


@permiso_requerido("caja", "ver")
def caja_movimientos(request):
    turno = _turno_abierto(request.user)
    if request.GET.get("turno", "").isdigit():
        qs = TurnoCaja.objects.select_related("caja", "usuario")
        if not request.user.tiene_permiso("caja", "supervisar"):
            qs = qs.filter(usuario=request.user)
        turno = get_object_or_404(qs, pk=int(request.GET["turno"]))
    if turno is None:
        messages.warning(request, "Abre un turno de caja para consultar sus movimientos.")
        return redirect(f"{_ns(request)}:caja_abrir")
    form = MovimientoCajaForm(request.POST or None)
    if request.method == "POST":
        if turno.estado != "abierta":
            messages.error(request, "El turno está cerrado; no admite movimientos.")
        elif form.is_valid():
            try:
                movimiento = services.registrar_movimiento(
                    turno, request.user, form.cleaned_data["tipo"], form.cleaned_data["monto"],
                    form.cleaned_data["descripcion"],
                )
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            else:
                registrar(request, "movimiento_caja", "caja", movimiento,
                          f"{movimiento.get_tipo_display()} de S/ {movimiento.monto:.2f}: {movimiento.descripcion}")
                messages.success(request, "Movimiento registrado.")
                return redirect(f"{_ns(request)}:caja_movimientos")
        else:
            messages.error(request, "Revisa los datos del movimiento.")
    movimientos = turno.movimientos.select_related("metodo_pago", "venta", "creado_por").order_by("creado", "id")
    return render(request, "ventas/caja_movimientos.html", {
        "turno": turno, "movimientos": movimientos, "form": form,
        "esperado": turno.efectivo_calculado(),
        "puede_mover": request.user.tiene_permiso("caja", "mover") and turno.estado == "abierta",
    })


@permiso_requerido("caja", "cerrar")
def caja_cerrar(request):
    turno = _turno_abierto(request.user)
    if turno is None and request.GET.get("turno", "").isdigit():
        qs = TurnoCaja.objects.select_related("caja", "usuario", "cerrado_por")
        if not request.user.tiene_permiso("caja", "supervisar"):
            qs = qs.filter(usuario=request.user)
        turno = get_object_or_404(qs, pk=int(request.GET["turno"]))
    if turno is None:
        messages.warning(request, "No tienes un turno abierto para cerrar.")
        return redirect(f"{_ns(request)}:caja_abrir")
    inicial = turno.efectivo_calculado() if turno.estado == "abierta" else turno.monto_contado
    form = CierreCajaForm(request.POST or None, initial={"monto_contado": inicial})
    if request.method == "POST" and turno.estado == "abierta":
        if form.is_valid():
            try:
                turno = services.cerrar_caja(
                    turno, request.user, form.cleaned_data["monto_contado"],
                    form.cleaned_data.get("observacion", ""),
                )
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            else:
                registrar(request, "cerrar_caja", "caja", turno,
                          f"Cerró la caja {turno.caja.nombre}: esperado S/ {turno.efectivo_esperado:.2f}, "
                          f"contado S/ {turno.monto_contado:.2f}, diferencia S/ {turno.diferencia:.2f}")
                messages.success(request, "Caja cerrada. El cierre quedó registrado.")
                return redirect(f"{reverse('ventas:caja_cerrar')}?turno={turno.pk}")
        else:
            messages.error(request, "Revisa los datos del cierre.")
    movimientos = turno.movimientos.select_related("metodo_pago", "venta", "creado_por").order_by("creado", "id")
    return render(request, "ventas/caja_cerrar.html", {
        "turno": turno, "form": form, "movimientos": movimientos,
        "esperado": turno.efectivo_calculado() if turno.estado == "abierta" else turno.efectivo_esperado,
        "puede_cerrar": turno.estado == "abierta",
    })


@permiso_requerido("caja", "supervisar")
def cajas(request):
    qs = TurnoCaja.objects.select_related("caja", "usuario", "cerrado_por")
    estado = request.GET.get("estado", "")
    usuario = request.GET.get("usuario", "")
    if estado:
        qs = qs.filter(estado=estado)
    if usuario.isdigit():
        qs = qs.filter(usuario_id=int(usuario))
    qs = _rango_fechas(request, qs, "fecha_apertura")
    pagina, parametros = paginar(request, qs, 20)
    return render(request, "ventas/cajas.html", {
        "pagina": pagina, "qs": parametros, "f": request.GET,
        "usuarios": Usuario.objects.filter(turnos_caja__isnull=False).distinct().order_by("first_name"),
        "estados": TurnoCaja.ESTADOS,
    })


@permiso_requerido("metodos_pago", "ver")
def metodos_pago(request):
    return render(request, "ventas/metodos_pago.html", {
        "metodos": MetodoPago.objects.all(),
        "puede_editar": request.user.tiene_permiso("metodos_pago", "editar"),
        "puede_crear": request.user.tiene_permiso("metodos_pago", "crear"),
        "puede_desactivar": request.user.tiene_permiso("metodos_pago", "desactivar"),
    })


@permiso_requerido("metodos_pago", "crear")
def metodo_pago_crear(request):
    form = MetodoPagoForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            metodo = form.save()
            registrar(request, "crear", "metodos_pago", metodo, f"Creó el método de pago {metodo.nombre}")
            messages.success(request, "Método de pago creado.")
            return redirect("ventas:metodos_pago")
        messages.error(request, "Revisa los datos del método de pago.")
    return render(request, "ventas/metodo_pago_form.html", {"form": form, "editando": None})


@permiso_requerido("metodos_pago", "editar")
def metodo_pago_editar(request, pk):
    metodo = get_object_or_404(MetodoPago, pk=pk)
    form = MetodoPagoForm(request.POST or None, instance=metodo)
    if request.method == "POST":
        if form.is_valid():
            metodo = form.save()
            registrar(request, "editar", "metodos_pago", metodo, f"Editó el método de pago {metodo.nombre}")
            messages.success(request, "Método de pago actualizado.")
            return redirect("ventas:metodos_pago")
        messages.error(request, "Revisa los datos del método de pago.")
    return render(request, "ventas/metodo_pago_form.html", {"form": form, "editando": metodo})


@require_POST
@permiso_requerido("metodos_pago", "desactivar")
def metodo_pago_estado(request, pk):
    metodo = get_object_or_404(MetodoPago, pk=pk)
    metodo.activo = not metodo.activo
    metodo.save(update_fields=["activo"])
    registrar(request, "activar" if metodo.activo else "desactivar", "metodos_pago", metodo,
              f"{'Activó' if metodo.activo else 'Desactivó'} el método de pago {metodo.nombre}")
    messages.success(request, "Método de pago actualizado.")
    return redirect("ventas:metodos_pago")


@permiso_requerido("mesas", "ver")
def caja_mesas(request):
    """Lista mesas activas con sus cuentas abiertas y detalles de consumo (panel caja)."""
    mesas = list(Mesa.objects.filter(activa=True).order_by("numero"))
    filas = []
    for mesa in mesas:
        cuenta = services.cuenta_abierta_de_mesa(mesa.pk)
        pedidos = []
        total = Decimal("0.00")
        if cuenta is not None:
            pedidos = list(
                cuenta.pedidos.select_related("mesa")
                .prefetch_related("detalles__producto")
                .exclude(estado="cancelado")
                .order_by("ronda", "creado")
            )
            total = sum((p.total for p in pedidos), Decimal("0.00"))
        filas.append({
            "mesa": mesa,
            "cuenta": cuenta,
            "pedidos": pedidos,
            "total": total,
            "ocupada": cuenta is not None,
        })
    return render(request, "ventas/caja_mesas.html", {"filas": filas})


@permiso_requerido("ventas", "crear")
def caja_cobrar_cuenta(request, pk):
    turno = _turno_abierto(request.user)
    if turno is None:
        messages.warning(request, "Primero abre tu turno de caja para cobrar.")
        return redirect(f"{reverse('caja:caja_abrir')}?next=caja_cobrar_cuenta")
    cuenta = get_object_or_404(CuentaMesa, pk=pk)
    try:
        venta, creada = services.obtener_o_crear_venta_cuenta(request.user, turno, cuenta)
    except ValidationError as exc:
        for mensaje in exc.messages:
            messages.error(request, mensaje)
        return redirect("mesero:cuenta_detalle", pk=cuenta.pk)
    if creada:
        registrar(request, "venta", "ventas", venta, f"Registró la venta {venta.numero} de la mesa {cuenta.mesa}")
        messages.success(request, f"Venta {venta.numero} registrada para la mesa {cuenta.mesa}.")
    else:
        messages.info(request, f"La venta {venta.numero} ya existía para la mesa {cuenta.mesa}.")
    return redirect(f"{_ns(request)}:venta_detalle", pk=venta.pk)

@permiso_requerido("ventas", "ver")
def caja_cuenta_json(request, pk):
    cuenta = get_object_or_404(CuentaMesa.objects.select_related("mesa", "venta"), pk=pk)
    try:
        venta = cuenta.venta
    except Exception:
        venta = None
    return JsonResponse({
        "cuenta": {"id": cuenta.pk, "estado": cuenta.estado, "mesa": str(cuenta.mesa)},
        "venta": {
            "id": venta.pk if venta is not None else None,
            "numero": venta.numero if venta is not None else None,
            "estado_pago": venta.estado_pago if venta is not None else None,
            "total": str(venta.total) if venta is not None else None,
            "pagado": str(venta.total_pagado) if venta is not None else None,
        },
    })
