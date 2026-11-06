from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cuentas.permisos import permiso_requerido
from apps.nucleo.auditoria import registrar
from apps.ventas import services
from apps.ventas.models import IncidenciaCocina, Pedido, Producto

SIGUIENTE_ESTADO = {
    "pendiente": "en_preparacion",
    "en_preparacion": "listo",
    "listo": "entregado",
}


@permiso_requerido("cocina", "ver")
def tablero(request):
    pedidos = (
        Pedido.objects.select_related("mesa", "creado_por")
        .prefetch_related("detalles")
        .exclude(estado__in=["entregado", "cancelado"])
        .order_by("creado")
    )
    columnas = [
        ("pendiente", "Pendientes", [p for p in pedidos if p.estado == "pendiente"]),
        ("en_preparacion", "En preparación", [p for p in pedidos if p.estado == "en_preparacion"]),
        ("listo", "Listos", [p for p in pedidos if p.estado == "listo"]),
    ]
    return render(request, "cocina/tablero.html", {
        "columnas": columnas,
        "total_activos": len(pedidos),
        "puede_actualizar": request.user.tiene_permiso("cocina", "actualizar"),
    })


@permiso_requerido("cocina", "ver")
def pedido_detalle(request, pk):
    pedido = get_object_or_404(
        Pedido.objects.select_related("mesa", "creado_por").prefetch_related("detalles"),
        pk=pk,
    )
    return render(request, "cocina/pedido_detalle.html", {
        "pedido": pedido,
        "siguiente": SIGUIENTE_ESTADO.get(pedido.estado),
        "puede_actualizar": request.user.tiene_permiso("cocina", "actualizar"),
    })


@require_POST
@permiso_requerido("cocina", "actualizar")
def avanzar(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    siguiente = SIGUIENTE_ESTADO.get(pedido.estado)
    if not siguiente:
        messages.info(request, "Este pedido ya no tiene un siguiente estado en cocina.")
        return redirect("cocina:tablero")
    try:
        services.cambiar_estado_pedido(pedido, siguiente)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("cocina:pedido_detalle", pk=pedido.pk)
    registrar(
        request, "pedido_estado", "cocina", pedido,
        f"Cocina cambió el pedido {pedido.numero} a {pedido.get_estado_display()}",
    )
    messages.success(request, f"Pedido {pedido.numero}: {pedido.get_estado_display()}.")
    return redirect("cocina:tablero")


@permiso_requerido("cocina", "ver")
def historial(request):
    qs = Pedido.objects.select_related("mesa", "creado_por").prefetch_related("detalles").filter(
        estado__in=["entregado", "cancelado"]
    ).order_by("-actualizado")
    return render(request, "cocina/historial.html", {"pedidos": qs})


@permiso_requerido("cocina", "ver")
def agotados(request):
    incidencias = IncidenciaCocina.objects.select_related("producto", "pedido", "creado_por").order_by("-creado")[:50]
    productos = Producto.objects.filter(activo=True).order_by("nombre")
    return render(request, "cocina/agotados.html", {"incidencias": incidencias, "productos": productos})


@require_POST
@permiso_requerido("cocina", "actualizar")
def reportar_agotado(request):
    producto_id = request.POST.get("producto")
    descripcion = " ".join((request.POST.get("descripcion") or "").split())[:300] or "Producto agotado"
    producto = None
    if producto_id and producto_id.isdigit():
        producto = Producto.objects.filter(pk=producto_id).first()
    pedido_id = request.POST.get("pedido")
    pedido = None
    if pedido_id and pedido_id.isdigit():
        pedido = Pedido.objects.filter(pk=pedido_id).first()
    IncidenciaCocina.objects.create(
        pedido=pedido, producto=producto, tipo="producto_agotado",
        descripcion=descripcion, creado_por=request.user,
    )
    registrar(request, "reportar_agotado", "cocina", producto,
              f"Reportó agotado: {producto.nombre if producto else descripcion}")
    messages.success(request, "Incidencia registrada.")
    return redirect("cocina:agotados")


@require_POST
@permiso_requerido("cocina", "ver")
def cambiar_estado_incidencia(request, pk):
    incidencia = get_object_or_404(IncidenciaCocina, pk=pk)
    nuevo_estado = request.POST.get("estado")
    if nuevo_estado in dict(IncidenciaCocina.ESTADOS):
        incidencia.estado = nuevo_estado
        incidencia.save(update_fields=["estado"])
        registrar(request, "cambiar_estado_incidencia", "cocina", incidencia,
                  f"Cambió estado de incidencia {incidencia.pk} a {nuevo_estado}")
        messages.success(request, f"Estado actualizado a {incidencia.get_estado_display()}.")
    return redirect("cocina:agotados")


@require_POST
@permiso_requerido("cocina", "ver")
def agregar_observacion_incidencia(request, pk):
    incidencia = get_object_or_404(IncidenciaCocina, pk=pk)
    observacion = request.POST.get("observacion", "").strip()
    if observacion:
        incidencia.observacion_dueno = observacion
        incidencia.save(update_fields=["observacion_dueno"])
        registrar(request, "agregar_observacion_incidencia", "cocina", incidencia,
                  f"Agregó observación a incidencia {incidencia.pk}")
        messages.success(request, "Observación guardada.")
    return redirect("cocina:agotados")


@permiso_requerido("cocina", "ver")
def tablero_json(request):
    pedidos = (
        Pedido.objects.select_related("mesa")
        .exclude(estado__in=["entregado", "cancelado"])
        .order_by("creado")
    )
    data = []
    ultimo = None
    for p in pedidos:
        if ultimo is None or (p.actualizado and p.actualizado > ultimo):
            ultimo = p.actualizado
        data.append({
            "id": p.pk,
            "numero": p.numero,
            "estado": p.estado,
            "mesa": str(p.mesa) if p.mesa else "",
            "origen": p.origen,
            "prioridad": p.prioridad,
            "creado": p.creado.isoformat() if p.creado else "",
            "actualizado": p.actualizado.isoformat() if p.actualizado else "",
            "total": str(p.total),
            "ronda": p.ronda,
        })
    return JsonResponse({"pedidos": data, "actualizado": (ultimo.isoformat() if ultimo else "")})
