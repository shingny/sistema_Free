import csv

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cuentas.permisos import permiso_requerido
from apps.nucleo.auditoria import cambios, registrar, valores
from apps.nucleo.utils import paginar

from .forms import CategoriaForm, ProductoForm
from .models import Categoria, Producto

CAMPOS_PRODUCTO = ["nombre", "descripcion", "categoria", "precio", "imagen", "activo"]
CAMPOS_CATEGORIA = ["nombre", "descripcion", "orden", "activo"]


# --------------------------------------------------------------- Categorías
@permiso_requerido("categorias", "ver")
def categorias(request):
    qs = Categoria.objects.annotate(
        total=Count("productos"), activos=Count("productos", filter=Q(productos__activo=True))
    )
    return render(request, "catalogo/categorias.html", {"categorias": qs})


@permiso_requerido("categorias", "crear")
def categoria_crear(request):
    form = CategoriaForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            categoria = form.save()
            registrar(request, "crear", "categorias", categoria, f"Creó la categoría {categoria.nombre}",
                      despues=valores(categoria, CAMPOS_CATEGORIA))
            messages.success(request, "Categoría creada.")
            return redirect("catalogo:categorias")
        messages.error(request, "Revisa los campos marcados.")
    return render(request, "catalogo/categoria_form.html", {"form": form, "editando": None})


@permiso_requerido("categorias", "editar")
def categoria_editar(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    antes = valores(categoria, CAMPOS_CATEGORIA)
    form = CategoriaForm(request.POST or None, instance=categoria)
    if request.method == "POST":
        if form.is_valid():
            categoria = form.save()
            a, d = cambios(antes, valores(categoria, CAMPOS_CATEGORIA))
            if d:
                registrar(request, "editar", "categorias", categoria, f"Editó la categoría {categoria.nombre}", a, d)
            messages.success(request, "Categoría actualizada.")
            return redirect("catalogo:categorias")
        messages.error(request, "Revisa los campos marcados.")
    return render(request, "catalogo/categoria_form.html", {"form": form, "editando": categoria})


@require_POST
@permiso_requerido("categorias", "desactivar")
def categoria_estado(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if categoria.activo:
        if categoria.productos.filter(activo=True).exists():
            messages.error(request, "Desactiva primero los productos activos de esta categoría.")
            return redirect("catalogo:categorias")
        categoria.activo = False
        accion, texto = "desactivar", "desactivada"
    else:
        categoria.activo = True
        accion, texto = "activar", "activada"
    categoria.save(update_fields=["activo", "actualizado"])
    registrar(request, accion, "categorias", categoria, f"Categoría {categoria.nombre} {texto}",
              {"activo": not categoria.activo}, {"activo": categoria.activo})
    messages.success(request, f"Categoría {texto}.")
    return redirect("catalogo:categorias")


# ----------------------------------------------------------------- Productos
def _productos_filtrados(request):
    qs = Producto.objects.select_related("categoria")
    q = request.GET.get("q", "").strip()
    categoria = request.GET.get("categoria", "")
    estado = request.GET.get("estado", "")
    if q:
        qs = qs.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))
    if categoria.isdigit():
        qs = qs.filter(categoria_id=int(categoria))
    if estado == "activo":
        qs = qs.filter(activo=True)
    elif estado == "inactivo":
        qs = qs.filter(activo=False)
    return qs, {"q": q, "categoria": categoria, "estado": estado}


@permiso_requerido("productos", "ver")
def productos(request):
    qs, filtros = _productos_filtrados(request)
    pagina, parametros = paginar(request, qs)
    return render(request, "catalogo/productos.html", {
        "pagina": pagina, "qs": parametros, "f": filtros, "categorias": Categoria.objects.all(),
        "puede_exportar": request.user.tiene_permiso("productos", "reportes"),
    })


@permiso_requerido("productos", "crear")
def producto_crear(request):
    form = ProductoForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            producto = form.save()
            registrar(request, "crear", "productos", producto, f"Creó el producto {producto.nombre}",
                      despues=valores(producto, CAMPOS_PRODUCTO))
            messages.success(request, "Producto creado.")
            return redirect("catalogo:productos")
        messages.error(request, "Revisa los campos marcados.")
    return render(request, "catalogo/producto_form.html",
                  {"form": form, "editando": None, "hay_categorias": Categoria.objects.filter(activo=True).exists()})


@permiso_requerido("productos", "editar")
def producto_editar(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    antes = valores(producto, CAMPOS_PRODUCTO)
    form = ProductoForm(request.POST or None, request.FILES or None, instance=producto)
    if request.method == "POST":
        if form.is_valid():
            objeto = form.save(commit=False)
            if form.cleaned_data.get("quitar_imagen") and not request.FILES.get("imagen"):
                objeto.imagen = ""
            objeto.save()
            a, d = cambios(antes, valores(objeto, CAMPOS_PRODUCTO))
            if d:
                if "precio" in d:
                    registrar(request, "cambio_precio", "productos", objeto,
                              f"Cambió el precio de {objeto.nombre}: S/ {a['precio']} → S/ {d['precio']}",
                              {"precio": a["precio"]}, {"precio": d["precio"]})
                resto_a = {k: v for k, v in a.items() if k != "precio"}
                resto_d = {k: v for k, v in d.items() if k != "precio"}
                if resto_d:
                    registrar(request, "editar", "productos", objeto, f"Editó el producto {objeto.nombre}",
                              resto_a, resto_d)
            messages.success(request, "Producto actualizado.")
            return redirect("catalogo:productos")
        messages.error(request, "Revisa los campos marcados.")
    return render(request, "catalogo/producto_form.html",
                  {"form": form, "editando": producto, "hay_categorias": True})


@require_POST
@permiso_requerido("productos", "desactivar")
def producto_estado(request, pk):
    producto = get_object_or_404(Producto.objects.select_related("categoria"), pk=pk)
    if not producto.activo and not producto.categoria.activo:
        messages.error(request, "Activa primero la categoría de este producto.")
        return redirect("catalogo:productos")
    producto.activo = not producto.activo
    producto.save(update_fields=["activo", "actualizado"])
    texto = "activado" if producto.activo else "desactivado"
    registrar(request, "activar" if producto.activo else "desactivar", "productos", producto,
              f"Producto {producto.nombre} {texto}", {"activo": not producto.activo}, {"activo": producto.activo})
    messages.success(request, f"Producto {texto}." + ("" if producto.activo else " Ya no estará disponible en nuevas ventas."))
    return redirect("catalogo:productos")


@permiso_requerido("productos", "reportes")
def productos_exportar(request):
    qs, _ = _productos_filtrados(request)
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="productos.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(["Id", "Nombre", "Categoría", "Precio (PEN)", "Estado", "Descripción"])
    for p in qs:
        escritor.writerow([p.pk, p.nombre, p.categoria.nombre, f"{p.precio:.2f}",
                           "Activo" if p.activo else "Inactivo", p.descripcion])
    registrar(request, "exportar", "productos", descripcion="Exportó productos a CSV")
    return respuesta
