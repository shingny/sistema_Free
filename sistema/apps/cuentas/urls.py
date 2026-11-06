from django.urls import path

from . import views

app_name = "cuentas"

urlpatterns = [
    path("ingresar/", views.login_view, name="login"),
    path("salir/", views.logout_view, name="logout"),
    path("perfil/", views.perfil, name="perfil"),
    path("perfil/contrasena/", views.cambiar_password, name="cambiar_password"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views.usuario_crear, name="usuario_crear"),
    path("usuarios/<int:pk>/editar/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/estado/", views.usuario_estado, name="usuario_estado"),
    path("usuarios/<int:pk>/restablecer/", views.usuario_restablecer, name="usuario_restablecer"),
    path("roles/", views.roles, name="roles"),
    path("roles/<int:pk>/permisos/", views.rol_permisos, name="rol_permisos"),
]
