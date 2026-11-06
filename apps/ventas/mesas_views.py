from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cuentas.permisos import denegar, permiso_requerido
from apps.nucleo.auditoria import registrar
from apps.ventas.forms import MesaForm
from apps.ventas.models import CuentaMesa, Mesa
from apps.ventas.services import cuenta_abierta_de_mesa


def _estado_mesa(mesa):
    cuenta = cuenta_abierta_de_mesa(mesa.pk)
    if cuenta is not None:
        return "ocupada", cuenta
    if not mesa.activa:
        return "inactiva", None
    return "libre", None


@permiso_requerido("mesas", "ver")
def mesa_detalle(request, pk):
    mesa = get_object_or_404(Mesa, pk=pk)
    estado, cuenta = _estado_mesa(mesa)
    pedidos = []
    if cuenta is not None:
        pedidos = list(
            cuenta.pedidos.select_related("mesa").prefetch_related("detalles__producto").order_by("ronda", "creado")
        )
    return render(request, "ventas/mesa_detalle.html", {
        "mesa": mesa,
        "estado": estado,
        "cuenta": cuenta,
        "pedidos": pedidos,
    })


@permiso_requerido("mesas", "ver")
def mesas_lista(request):
    mesas = list(Mesa.objects.order_by("numero"))
    filas = []
    for mesa in mesas:
        estado, cuenta = _estado_mesa(mesa)
        pedidos = []
        if cuenta is not None:
            pedidos = list(
                cuenta.pedidos.select_related("mesa").prefetch_related("detalles__producto").order_by("ronda", "creado")
            )
        filas.append({
            "mesa": mesa,
            "estado": estado,
            "cuenta": cuenta,
            "pedidos": pedidos,
        })
    return render(request, "ventas/mesas_lista.html", {
        "filas": filas,
        "puede_gestionar": request.user.tiene_permiso("mesas", "gestionar"),
    })


@permiso_requerido("mesas", "gestionar")
def mesa_crear(request):
    form = MesaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        mesa = form.save()
        registrar(request, "crear", "mesas", mesa, f"Creó la mesa {mesa}")
        messages.success(request, "Mesa creada correctamente.")
        return redirect("ventas:mesas_lista")
    if request.method == "POST":
        messages.error(request, "Revisa los datos de la mesa.")
    return render(request, "ventas/mesa_form.html", {"form": form, "editando": None})


@permiso_requerido("mesas", "gestionar")
def mesa_editar(request, pk):
    mesa = get_object_or_404(Mesa, pk=pk)
    form = MesaForm(request.POST or None, instance=mesa)
    if request.method == "POST" and form.is_valid():
        mesa = form.save()
        registrar(request, "editar", "mesas", mesa, f"Editó la mesa {mesa}")
        messages.success(request, "Mesa actualizada.")
        return redirect("ventas:mesas_lista")
    if request.method == "POST":
        messages.error(request, "Revisa los datos de la mesa.")
    return render(request, "ventas/mesa_form.html", {"form": form, "editando": mesa})


@require_POST
@permiso_requerido("mesas", "gestionar")
def mesa_estado(request, pk):
    mesa = get_object_or_404(Mesa, pk=pk)
    mesa.activa = not mesa.activa
    mesa.save(update_fields=["activa"])
    registrar(request, "activar" if mesa.activa else "desactivar", "mesas", mesa,
              f"{'Activó' if mesa.activa else 'Desactivó'} la mesa {mesa}")
    messages.success(request, "Estado de la mesa actualizado.")
    return redirect("ventas:mesas_lista")