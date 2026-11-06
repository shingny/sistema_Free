from django.urls import path

from . import mesero_views

app_name = "mesero"

urlpatterns = [
    path("", mesero_views.mesero_inicio, name="inicio"),
    path("pedido-rapido/", mesero_views.mesero_pedido_rapido, name="pedido_rapido"),
    path("mesas/", mesero_views.mesero_mesas, name="mesas"),
    path("mesas/<int:pk>/abrir/", mesero_views.mesero_mesa_abrir, name="mesa_abrir"),
    path("cuentas/<int:pk>/", mesero_views.mesero_cuenta_detalle, name="cuenta_detalle"),
    path("cuentas/<int:pk>/agregar/", mesero_views.mesero_cuenta_agregar, name="cuenta_agregar"),
    path("cuentas/<int:pk>/cobrar/", mesero_views.mesero_cuenta_cobrar, name="cuenta_cobrar"),
    path("cuentas/<int:pk>/cerrar/", mesero_views.mesero_cuenta_cerrar, name="cuenta_cerrar"),
    path("pedidos/activos/", mesero_views.mesero_pedidos_activos, name="pedidos_activos"),
    path("pedidos/listos/", mesero_views.mesero_pedidos_listos, name="pedidos_listos"),
    path("historial/", mesero_views.mesero_historial, name="historial"),
    path("api/cuentas/<int:pk>/", mesero_views.cuenta_json, name="cuenta_json"),
]