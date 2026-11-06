import csv
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.db.models import Avg, Count, Q

from apps.cuentas.models import Rol, Usuario
from apps.cuentas.permisos import denegar, permiso_requerido
from apps.catalogo.models import Categoria, Producto
from apps.ventas.models import Pago, Pedido, TurnoCaja, Venta

from .auditoria import ETIQUETAS_ACCION, cambios, registrar, valores
from .forms import ConfiguracionForm
from .models import Auditoria, Configuracion
from .utils import paginar


@login_required
def inicio(request):
    if request.user.tiene_permiso("dashboard", "ver"):
        return redirect("nucleo:dashboard")
    if request.user.tiene_permiso("ventas", "ver") or request.user.tiene_permiso("caja", "ver"):
        return redirect("caja:inicio")
    if request.user.tiene_permiso("mesas", "abrir"):
        return redirect("mesero:inicio")
    if request.user.tiene_permiso("cocina", "ver"):
        return redirect("cocina:tablero")
    return render(request, "nucleo/inicio.html")


@permiso_requerido("dashboard", "ver")
def dashboard(request):
    config = Configuracion.obtener()
    actividad = []
    if request.user.tiene_permiso("auditoria", "ver"):
        actividad = Auditoria.objects.select_related("usuario")[:8]

    hoy = timezone.localdate()
    try:
        desde = datetime.strptime(request.GET.get("desde", ""), "%Y-%m-%d").date()
    except ValueError:
        desde = hoy
    try:
        hasta = datetime.strptime(request.GET.get("hasta", ""), "%Y-%m-%d").date()
    except ValueError:
        hasta = hoy
    if hasta < desde:
        desde, hasta = hasta, desde
    inicio = timezone.make_aware(datetime.combine(desde, time.min))
    fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min))

    puede_ventas = request.user.tiene_permiso("ventas", "reportes")
    ventas_periodo = Venta.objects.none()
    total_vendido = efectivo = electronico = 0
    operaciones = 0
    cajas_abiertas = cajas_cerradas = 0
    diferencia_total = 0
    turnos_con_diferencia = 0
    ventas_por_cajero = []
    pedidos_abiertos = 0
    if puede_ventas:
        ventas_periodo = Venta.objects.filter(
            estado="registrada", creada__gte=inicio, creada__lt=fin
        )
        total_vendido = ventas_periodo.aggregate(total=Sum("total"))["total"] or 0
        operaciones = ventas_periodo.count()
        pagos = Pago.objects.filter(venta__in=ventas_periodo, estado="verificado")
        efectivo = pagos.filter(metodo__afecta_efectivo=True).aggregate(total=Sum("monto"))["total"] or 0
        electronico = pagos.filter(metodo__afecta_efectivo=False).aggregate(total=Sum("monto"))["total"] or 0
        cajas_abiertas = TurnoCaja.objects.filter(estado="abierta").count()
        turnos_cerrados = TurnoCaja.objects.filter(
            estado="cerrada", fecha_cierre__gte=inicio, fecha_cierre__lt=fin
        )
        cajas_cerradas = turnos_cerrados.count()
        diferencia_total = turnos_cerrados.aggregate(total=Sum("diferencia"))["total"] or 0
        turnos_con_diferencia = turnos_cerrados.exclude(diferencia=0).count()
        ventas_por_cajero = ventas_periodo.values(
            "cajero__first_name", "cajero__last_name", "cajero__username"
        ).annotate(total=Sum("total"), operaciones=Count("id")).order_by("-total")
        pedidos_abiertos = Pedido.objects.filter(
            estado__in=["pendiente", "en_preparacion", "listo"]
        ).count()

    contexto = {
        "total_usuarios": Usuario.objects.count(),
        "usuarios_activos": Usuario.objects.filter(is_active=True).count(),
        "productos_activos": Producto.objects.filter(activo=True).count(),
        "productos_total": Producto.objects.count(),
        "categorias_total": Categoria.objects.count(),
        "categorias_activas": Categoria.objects.filter(activo=True).count(),
        "por_rol": Rol.objects.annotate(
            n=Count("usuarios", filter=Q(usuarios__is_active=True))
        ).order_by("-nivel"),
        "pendientes": config.campos_pendientes(),
        "actividad": actividad,
        "puede_ventas": puede_ventas,
        "total_vendido": total_vendido,
        "operaciones": operaciones,
        "efectivo": efectivo,
        "electronico": electronico,
        "cajas_abiertas": cajas_abiertas,
        "cajas_cerradas": cajas_cerradas,
        "diferencia_total": diferencia_total,
        "turnos_con_diferencia": turnos_con_diferencia,
        "ventas_por_cajero": ventas_por_cajero,
        "pedidos_abiertos": pedidos_abiertos,
        "desde": desde.strftime("%Y-%m-%d"),
        "hasta": hasta.strftime("%Y-%m-%d"),
    }
    return render(request, "nucleo/dashboard.html", contexto)


@permiso_requerido("configuracion", "ver")
def configuracion(request):
    config = Configuracion.obtener()
    puede_editar = request.user.tiene_permiso("configuracion", "editar")
    campos = ["nombre_comercial", "razon_social", "ruc", "direccion", "telefono", "correo",
              "horario_atencion", "permitir_pago_parcial"]
    if request.method == "POST":
        if not puede_editar:
            return denegar(request, "configuracion", "editar")
        antes = valores(config, campos)
        form = ConfiguracionForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            objeto = form.save(commit=False)
            if form.cleaned_data.get("quitar_logo") and not request.FILES.get("logo"):
                objeto.logo = ""
            objeto.actualizado_por = request.user
            objeto.save()
            a, d = cambios(antes, valores(objeto, campos))
            if d:
                registrar(request, "editar", "configuracion", objeto,
                          "Actualizó la configuración general", a, d)
            messages.success(request, "Configuración guardada.")
            return redirect("nucleo:configuracion")
        messages.error(request, "Revisa los campos marcados.")
    else:
        form = ConfiguracionForm(instance=config)
    return render(request, "nucleo/configuracion.html", {"form": form, "puede_editar": puede_editar, "config_obj": config})


def _auditoria_filtrada(request):
    qs = Auditoria.objects.select_related("usuario")
    g = request.GET
    if g.get("usuario", "").isdigit():
        qs = qs.filter(usuario_id=int(g["usuario"]))
    if g.get("modulo"):
        qs = qs.filter(modulo=g["modulo"])
    if g.get("accion"):
        qs = qs.filter(accion=g["accion"])
    if g.get("q"):
        qs = qs.filter(Q(descripcion__icontains=g["q"]) | Q(usuario_nombre__icontains=g["q"]))
    for clave, esdesde in (("desde", True), ("hasta", False)):
        try:
            dia = datetime.strptime(g.get(clave, ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        if esdesde:
            qs = qs.filter(fecha__gte=timezone.make_aware(datetime.combine(dia, time.min)))
        else:
            qs = qs.filter(fecha__lt=timezone.make_aware(datetime.combine(dia + timedelta(days=1), time.min)))
    return qs


@permiso_requerido("auditoria", "ver")
def actividad(request):
    pagina, qs = paginar(request, _auditoria_filtrada(request), 20)
    contexto = {
        "pagina": pagina, "qs": qs,
        "usuarios": Usuario.objects.order_by("first_name", "last_name"),
        "modulos": sorted(set(Auditoria.objects.values_list("modulo", flat=True))),
        "acciones": ETIQUETAS_ACCION,
        "f": request.GET,
        "puede_exportar": request.user.tiene_permiso("auditoria", "reportes"),
    }
    return render(request, "nucleo/actividad.html", contexto)


@permiso_requerido("auditoria", "reportes")
def actividad_exportar(request):
    filas = _auditoria_filtrada(request)[:5000]
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="actividad.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(["Fecha (Lima)", "Usuario", "Módulo", "Acción", "Descripción", "IP"])
    for r in filas:
        escritor.writerow([
            timezone.localtime(r.fecha).strftime("%d/%m/%Y %H:%M:%S"), r.usuario_nombre, r.modulo,
            ETIQUETAS_ACCION.get(r.accion, r.accion), r.descripcion, r.ip or "",
        ])
    registrar(request, "exportar", "auditoria", descripcion="Exportó la actividad a CSV")
    return respuesta


@permiso_requerido("dashboard", "ver")
def pedidos_supervision(request):
    qs = Pedido.objects.select_related("mesa", "creado_por", "cuenta").prefetch_related("detalles")
    estado = request.GET.get("estado", "")
    origen = request.GET.get("origen", "")
    if estado:
        qs = qs.filter(estado=estado)
    if origen:
        qs = qs.filter(origen=origen)
    qs = qs.order_by("-creado")
    pagina, parametros = paginar(request, qs, 20)

    base = Pedido.objects.all()
    por_estado = base.values("estado").annotate(n=Count("id")).order_by("estado")
    por_modalidad = base.values("origen").annotate(n=Count("id"), total=Sum("total")).order_by("origen")
    # tiempo promedio de preparación: pedidos entregados con actualizado-creado
    entregados = base.filter(estado="entregado")
    tiempos = [ (p.actualizado - p.creado).total_seconds()/60 for p in entregados if p.actualizado and p.creado ]
    tiempo_promedio = (sum(tiempos)/len(tiempos)) if tiempos else 0

    meseros = base.values("creado_por__first_name", "creado_por__last_name", "creado_por__username").annotate(
        pedidos=Count("id"), total=Sum("total")
    ).order_by("-pedidos")[:10]

    return render(request, "nucleo/pedidos_supervision.html", {
        "pagina": pagina, "qs": parametros, "f": request.GET,
        "estados": Pedido.ESTADOS, "origenes": Pedido.ORIGENES,
        "por_estado": por_estado, "por_modalidad": por_modalidad,
        "tiempo_promedio": round(tiempo_promedio, 1),
        "meseros": meseros,
        "pedidos_activos": base.filter(estado__in=["pendiente", "en_preparacion", "listo"]).count(),
        "pedidos_cancelados": base.filter(estado="cancelado").count(),
    })
