from django.urls import path

from . import views

app_name = "cocina"

urlpatterns = [
    path("", views.tablero, name="tablero"),
    path("historial/", views.historial, name="historial"),
    path("productos-agotados/", views.agotados, name="agotados"),
    path("productos-agotados/reportar/", views.reportar_agotado, name="reportar_agotado"),
    path("incidencias/<int:pk>/estado/", views.cambiar_estado_incidencia, name="cambiar_estado_incidencia"),
    path("incidencias/<int:pk>/observacion/", views.agregar_observacion_incidencia, name="agregar_observacion_incidencia"),
    path("pedidos/<int:pk>/", views.pedido_detalle, name="pedido_detalle"),
    path("pedidos/<int:pk>/avanzar/", views.avanzar, name="avanzar"),
    path("api/tablero/", views.tablero_json, name="tablero_json"),
]
