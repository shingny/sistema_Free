from django.urls import path

from . import mesas_views, views

app_name = "ventas"

urlpatterns = [
    path("ventas/", views.inicio, name="inicio"),
    path("ventas/nueva/", views.nueva_venta, name="nueva_venta"),
    path("ventas/historial/", views.historial, name="historial"),
    path("ventas/<int:pk>/", views.venta_detalle, name="venta_detalle"),
    path("ventas/<int:pk>/ticket/", views.venta_ticket, name="venta_ticket"),
    path("ventas/<int:pk>/pagos/", views.venta_pago, name="venta_pago"),
    path("ventas/<int:pk>/anular/", views.venta_anular, name="venta_anular"),
    path("ventas/pagos/<int:pk>/verificar/", views.pago_verificar, name="pago_verificar"),
    path("ventas/pagos/<int:pk>/rechazar/", views.pago_rechazar, name="pago_rechazar"),
    path("ventas/pedidos/", views.pedidos, name="pedidos"),
    path("ventas/pedidos/<int:pk>/", views.pedido_detalle, name="pedido_detalle"),
    path("ventas/pedidos/<int:pk>/estado/", views.pedido_estado, name="pedido_estado"),
    path("ventas/caja/abrir/", views.caja_abrir, name="caja_abrir"),
    path("ventas/caja/movimientos/", views.caja_movimientos, name="caja_movimientos"),
    path("ventas/caja/cerrar/", views.caja_cerrar, name="caja_cerrar"),
    path("ventas/cajas/", views.cajas, name="cajas"),
    path("ventas/cuentas/<int:pk>/cobrar/", views.caja_cobrar_cuenta, name="caja_cobrar_cuenta"),
    path("ventas/cuentas/<int:pk>/estado-json/", views.caja_cuenta_json, name="caja_cuenta_json"),
    path("ventas/mesas/", mesas_views.mesas_lista, name="mesas_lista"),
    path("ventas/mesas/<int:pk>/detalle/", mesas_views.mesa_detalle, name="mesa_detalle"),
    path("ventas/mesas/nueva/", mesas_views.mesa_crear, name="mesa_crear"),
    path("ventas/mesas/<int:pk>/editar/", mesas_views.mesa_editar, name="mesa_editar"),
    path("ventas/mesas/<int:pk>/estado/", mesas_views.mesa_estado, name="mesa_estado"),
    path("ventas/metodos-pago/", views.metodos_pago, name="metodos_pago"),
    path("ventas/metodos-pago/nuevo/", views.metodo_pago_crear, name="metodo_pago_crear"),
    path("ventas/metodos-pago/<int:pk>/editar/", views.metodo_pago_editar, name="metodo_pago_editar"),
    path("ventas/metodos-pago/<int:pk>/estado/", views.metodo_pago_estado, name="metodo_pago_estado"),
]
