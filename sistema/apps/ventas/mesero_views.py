import json
import uuid
from decimal import Decimal

from django.contrib import messages
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.catalogo.models import Categoria, Producto
from apps.cuentas.permisos import denegar, permiso_requerido
from apps.nucleo.auditoria import registrar
from apps.nucleo.utils import paginar
from apps.ventas.models import CuentaMesa, Mesa, Pedido, Venta
from apps.ventas.services import (
    abrir_cuenta_mesa, cuenta_abierta_de_mesa, crear_ronda_pedido,
    solicitar_cobro_cuenta, cerrar_cuenta_mesa,
)


def _filas_mesas():
    """Arma las tarjetas de mesas con su cuenta abierta, total y número de rondas."""
    mesas = list(Mesa.objects.filter(activa=True).order_by("numero"))
    cuentas = {
        cuenta.mesa_id: cuenta
        for cuenta in CuentaMesa.objects.filter(
            estado__in=["abierta", "cobro_solicitado"]
        ).select_related("mesa").prefetch_related("pedidos")
    }
    filas = []
    for mesa in mesas:
        cuenta = cuentas.get(mesa.pk)
        pedidos = []
        total = Decimal("0.00")
        if cuenta is not None:
            pedidos = [p for p in cuenta.pedidos.all() if p.estado != "cancelado"]
            total = sum((p.total for p in pedidos), Decimal("0.00"))
        filas.append({
            "mesa": mesa,
            "cuenta": cuenta,
            "ocupada": cuenta is not None,
            "total": total,
            "rondas": len(pedidos),
        })
    return filas


@permiso_requerido("mesas", "ver")
def mesero_inicio(request):
    filas = _filas_mesas()
    categorias = Categoria.objects.filter(activo=True).prefetch_related(
        Prefetch(
            "productos",
            queryset=Producto.objects.disponibles().order_by("nombre"),
            to_attr="disponibles",
        )
    ).order_by("orden", "nombre")
    pedidos_activos = Pedido.objects.filter(
        creado_por=request.user, estado__in=["pendiente", "en_preparacion", "listo"]
    ).select_related("mesa", "cuenta").order_by("creado")[:8]
    return render(request, "mesero/inicio.html", {
        "filas": filas,
        "categorias": categorias,
        "pedidos_activos": pedidos_activos,
        "puede_abrir": request.user.tiene_permiso("mesas", "abrir"),
    })


@permiso_requerido("mesas", "ver")
def mesero_mesas(request):
    return render(request, "mesero/mesas.html", {
        "filas": _filas_mesas(),
        "puede_abrir": request.user.tiene_permiso("mesas", "abrir"),
    })


@require_POST
@permiso_requerido("mesas", "abrir")
def mesero_mesa_abrir(request, pk):
    mesa = get_object_or_404(Mesa, pk=pk, activa=True)
    try:
        cuenta, creada = abrir_cuenta_mesa(
            request.user, mesa,
            cliente_nombre=request.POST.get("cliente_nombre", ""),
            observacion=request.POST.get("observacion", ""),
        )
    except Exception as exc:  # ValidationError
        messages.error(request, getattr(exc, "messages", [str(exc)])[0])
        return redirect("mesero:mesas")
    if creada:
        registrar(request, "abrir", "mesas", cuenta, f"Abrió la mesa {mesa}")
        messages.success(request, f"Mesa {mesa} abierta.")
    else:
        messages.info(request, f"La mesa {mesa} ya tenía una cuenta abierta.")
    return redirect("mesero:cuenta_detalle", pk=cuenta.pk)


@permiso_requerido("mesas", "ver")
def mesero_cuenta_detalle(request, pk):
    cuenta = get_object_or_404(
        CuentaMesa.objects.select_related("mesa", "mesero", "venta").prefetch_related("pedidos__detalles"),
        pk=pk,
    )
    categorias = Categoria.objects.filter(activo=True).prefetch_related(
        # productos disponibles
    ).order_by("orden", "nombre")
    # attach disponibles manually
    for cat in categorias:
        cat.disponibles = list(Producto.objects.disponibles().filter(categoria=cat).order_by("nombre"))
    pedidos = list(cuenta.pedidos.order_by("ronda", "creado").prefetch_related("detalles"))
    pedidos_activos = [p for p in pedidos if p.estado != "cancelado"]
    total = sum((p.total for p in pedidos_activos), Decimal("0.00"))
    try:
        venta = cuenta.venta
    except Venta.DoesNotExist:
        venta = None
    puede_cerrar = request.user.tiene_permiso("mesas", "cerrar")
    return render(request, "mesero/cuenta_detalle.html", {
        "cuenta": cuenta,
        "categorias": categorias,
        "pedidos": pedidos,
        "pedidos_activos": pedidos_activos,
        "total": total,
        "venta": venta,
        "token": uuid.uuid4(),
        "puede_agregar": cuenta.estado == "abierta" and request.user.tiene_permiso("pedidos", "editar"),
        "puede_solicitar_cobro": cuenta.estado == "abierta" and bool(pedidos_activos) and puede_cerrar,
        "puede_liberar": cuenta.estado == "abierta" and not pedidos_activos and puede_cerrar,
    })


@require_POST
@permiso_requerido("pedidos", "editar")
def mesero_cuenta_agregar(request, pk):
    cuenta = get_object_or_404(CuentaMesa, pk=pk)
    if cuenta.estado != "abierta":
        messages.error(request, "La cuenta ya no admite nuevos pedidos. Solicita el cobro o libera la mesa.")
        return redirect("mesero:cuenta_detalle", pk=cuenta.pk)
    try:
        items = json.loads(request.POST.get("items", "[]"))
        if not isinstance(items, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        messages.error(request, "No se pudo leer el carrito.")
        return redirect("mesero:cuenta_detalle", pk=cuenta.pk)
    observacion = request.POST.get("observacion", "")
    prioridad = request.POST.get("prioridad", "normal")
    try:
        pedido, es_nueva = crear_ronda_pedido(request.user, cuenta, items, observacion=observacion, prioridad=prioridad)
    except Exception as exc:
        messages.error(request, getattr(exc, "messages", [str(exc)])[0])
        return redirect("mesero:cuenta_detalle", pk=cuenta.pk)
    if es_nueva:
        registrar(request, "pedido", "pedidos", pedido, f"Registró la ronda {pedido.ronda} del pedido {pedido.numero} en la mesa {cuenta.mesa}")
        messages.success(request, f"Pedido {pedido.numero} enviado a cocina (ronda {pedido.ronda}).")
    else:
        registrar(request, "pedido", "pedidos", pedido, f"Actualizó el pedido {pedido.numero} de la mesa {cuenta.mesa}")
        messages.success(request, f"Pedido {pedido.numero} actualizado.")
    return redirect("mesero:cuenta_detalle", pk=cuenta.pk)


@require_POST
@permiso_requerido("mesas", "ver")
@permiso_requerido("pedidos", "editar")
def mesero_pedido_rapido(request):
    """POS de mesas: abre la mesa si hace falta y agrega la ronda. Responde JSON."""
    try:
        mesa = Mesa.objects.get(pk=request.POST.get("mesa"), activa=True)
    except (Mesa.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Selecciona una mesa válida."}, status=400)
    try:
        items = json.loads(request.POST.get("items", "[]"))
        if not isinstance(items, list) or not items:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Agrega al menos un producto al pedido."}, status=400)

    cuenta = cuenta_abierta_de_mesa(mesa.pk)
    abierta_ahora = False
    if cuenta is None:
        if not request.user.tiene_permiso("mesas", "abrir"):
            return JsonResponse(
                {"ok": False, "error": "No tienes permiso para abrir mesas."}, status=403
            )
        cuenta, abierta_ahora = abrir_cuenta_mesa(request.user, mesa)
        if abierta_ahora:
            registrar(request, "abrir", "mesas", cuenta, f"Abrió la mesa {mesa}")

    if cuenta.estado != "abierta":
        return JsonResponse({
            "ok": False,
            "error": "La mesa tiene el cobro solicitado. Caja debe cobrar antes de agregar más productos.",
        }, status=400)

    try:
        pedido, es_nueva = crear_ronda_pedido(
            request.user, cuenta, items,
            observacion=request.POST.get("observacion", ""),
            prioridad=request.POST.get("prioridad", "normal"),
        )
    except Exception as exc:
        mensaje = getattr(exc, "messages", [str(exc)])[0]
        return JsonResponse({"ok": False, "error": mensaje}, status=400)

    if es_nueva:
        registrar(request, "pedido", "pedidos", pedido,
                  f"Registró la ronda {pedido.ronda} del pedido {pedido.numero} en la mesa {cuenta.mesa}")
    else:
        registrar(request, "pedido", "pedidos", pedido,
                  f"Actualizó el pedido {pedido.numero} de la mesa {cuenta.mesa}")

    pedidos = list(cuenta.pedidos.exclude(estado="cancelado"))
    total = sum((p.total for p in pedidos), Decimal("0.00"))
    return JsonResponse({
        "ok": True,
        "mesa": mesa.numero,
        "cuenta_id": cuenta.pk,
        "pedido": pedido.numero,
        "ronda": pedido.ronda,
        "es_nueva": es_nueva,
        "abierta_ahora": abierta_ahora,
        "rondas": len(pedidos),
        "total": f"{total:.2f}",
        "url_cuenta": reverse("mesero:cuenta_detalle", args=[cuenta.pk]),
    })


@require_POST
@permiso_requerido("mesas", "cerrar")
def mesero_cuenta_cobrar(request, pk):
    cuenta = get_object_or_404(CuentaMesa, pk=pk)
    try:
        solicitar_cobro_cuenta(cuenta, request.user)
    except Exception as exc:
        messages.error(request, getattr(exc, "messages", [str(exc)])[0])
        return redirect("mesero:cuenta_detalle", pk=cuenta.pk)
    registrar(request, "solicitar_cobro", "mesas", cuenta, f"Solicitó cobro de la mesa {cuenta.mesa}")
    messages.success(request, "Cobro solicitado. Caja puede procesar el pago.")
    return redirect("mesero:cuenta_detalle", pk=cuenta.pk)


@require_POST
@permiso_requerido("mesas", "cerrar")
def mesero_cuenta_cerrar(request, pk):
    cuenta = get_object_or_404(CuentaMesa, pk=pk)
    try:
        cerrar_cuenta_mesa(cuenta, request.user)
    except Exception as exc:
        messages.error(request, getattr(exc, "messages", [str(exc)])[0])
        return redirect("mesero:cuenta_detalle", pk=cuenta.pk)
    registrar(request, "cerrar", "mesas", cuenta, f"Cerró la cuenta de la mesa {cuenta.mesa}")
    messages.success(request, "Cuenta cerrada y mesa liberada.")
    return redirect("mesero:mesas")


@permiso_requerido("pedidos", "ver")
def mesero_pedidos_activos(request):
    qs = Pedido.objects.filter(
        creado_por=request.user, estado__in=["pendiente", "en_preparacion", "listo"]
    ).select_related("mesa", "cuenta").prefetch_related("detalles").order_by("creado")
    return render(request, "mesero/pedidos_activos.html", {"pedidos": qs})


@permiso_requerido("pedidos", "ver")
def mesero_pedidos_listos(request):
    qs = Pedido.objects.filter(
        creado_por=request.user, estado="listo"
    ).select_related("mesa", "cuenta").prefetch_related("detalles").order_by("creado")
    return render(request, "mesero/pedidos_listos.html", {"pedidos": qs})


@permiso_requerido("pedidos", "ver")
def mesero_historial(request):
    qs = Pedido.objects.filter(creado_por=request.user).select_related("mesa", "cuenta").order_by("-creado")
    pagina, parametros = paginar(request, qs, 20)
    return render(request, "mesero/historial.html", {"pagina": pagina, "qs": parametros})


@permiso_requerido("mesas", "ver")
def cuenta_json(request, pk):
    cuenta = get_object_or_404(CuentaMesa.objects.select_related("mesa", "venta"), pk=pk)
    try:
        venta = cuenta.venta
    except Exception:
        venta = None
    pedidos = []
    ultimo = None
    for p in cuenta.pedidos.order_by("ronda", "creado"):
        if ultimo is None or (p.actualizado and p.actualizado > ultimo):
            ultimo = p.actualizado
        pedidos.append({
            "id": p.pk,
            "ronda": p.ronda,
            "estado": p.estado,
            "total": str(p.total),
            "actualizado": p.actualizado.isoformat() if p.actualizado else "",
        })
    return JsonResponse({
        "cuenta": {
            "id": cuenta.pk,
            "estado": cuenta.estado,
            "mesa": str(cuenta.mesa),
        },
        "pedidos": pedidos,
        "total": str(sum((p.total for p in cuenta.pedidos.all() if p.estado != "cancelado"), Decimal("0.00"))),
        "venta": {
            "estado_pago": venta.estado_pago if venta is not None else None,
            "total": str(venta.total) if venta is not None else None,
        },
        "actualizado": (ultimo.isoformat() if ultimo else ""),
    })