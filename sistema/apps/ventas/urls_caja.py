from django.urls import path

from . import views

app_name = "caja"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("mesas/", views.caja_mesas, name="mesas"),
    path("nueva/", views.nueva_venta, name="nueva_venta"),
    path("historial/", views.historial, name="historial"),
    path("<int:pk>/", views.venta_detalle, name="venta_detalle"),
    path("<int:pk>/ticket/", views.venta_ticket, name="venta_ticket"),
    path("<int:pk>/pagos/", views.venta_pago, name="venta_pago"),
    path("<int:pk>/anular/", views.venta_anular, name="venta_anular"),
    path("pagos/<int:pk>/verificar/", views.pago_verificar, name="pago_verificar"),
    path("pagos/<int:pk>/rechazar/", views.pago_rechazar, name="pago_rechazar"),
    path("pedidos/", views.pedidos, name="pedidos"),
    path("pedidos/<int:pk>/", views.pedido_detalle, name="pedido_detalle"),
    path("pedidos/<int:pk>/estado/", views.pedido_estado, name="pedido_estado"),
    path("abrir/", views.caja_abrir, name="caja_abrir"),
    path("movimientos/", views.caja_movimientos, name="caja_movimientos"),
    path("cuentas/<int:pk>/cobrar/", views.caja_cobrar_cuenta, name="caja_cobrar_cuenta"),
    path("cerrar/", views.caja_cerrar, name="caja_cerrar"),
]
