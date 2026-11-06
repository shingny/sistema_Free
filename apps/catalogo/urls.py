from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/nueva/", views.categoria_crear, name="categoria_crear"),
    path("categorias/<int:pk>/editar/", views.categoria_editar, name="categoria_editar"),
    path("categorias/<int:pk>/estado/", views.categoria_estado, name="categoria_estado"),
    path("productos/", views.productos, name="productos"),
    path("productos/nuevo/", views.producto_crear, name="producto_crear"),
    path("productos/exportar/", views.productos_exportar, name="productos_exportar"),
    path("productos/<int:pk>/editar/", views.producto_editar, name="producto_editar"),
    path("productos/<int:pk>/estado/", views.producto_estado, name="producto_estado"),
]
