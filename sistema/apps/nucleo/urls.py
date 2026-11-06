from django.urls import path

from . import views

app_name = "nucleo"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("panel/", views.dashboard, name="dashboard"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("actividad/", views.actividad, name="actividad"),
    path("actividad/exportar/", views.actividad_exportar, name="actividad_exportar"),
    path("pedidos/", views.pedidos_supervision, name="pedidos_supervision"),
]
