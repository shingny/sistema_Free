import math
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.nucleo.auditoria import cambios, registrar, valores
from apps.nucleo.utils import paginar

from . import servicios
from .forms import CambiarPasswordForm, LoginForm, PerfilForm, UsuarioForm
from .models import Permiso, Rol, Usuario
from .permisos import (AYUDA_ACCION, CATALOGO_PERMISOS, NOMBRES_ACCION, NOMBRES_MODULO, denegar,
                       permisos_visibles, permiso_requerido, todos_los_permisos)

CAMPOS_USUARIO = ["first_name", "last_name", "documento", "username", "email", "telefono", "rol"]


# ------------------------------------------------------------------ Sesión
def _destino_panel(usuario):
    if usuario.tiene_permiso("dashboard", "ver"):
        return "nucleo:dashboard"
    if usuario.tiene_permiso("ventas", "ver") or usuario.tiene_permiso("caja", "ver"):
        return "caja:inicio"
    if usuario.tiene_permiso("mesas", "abrir"):
        return "mesero:inicio"
    if usuario.tiene_permiso("cocina", "ver"):
        return "cocina:tablero"
    return "nucleo:inicio"


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_destino_panel(request.user))
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        nombre = form.cleaned_data["username"].strip()
        clave = form.cleaned_data["password"]
        usuario = Usuario.objects.filter(username__iexact=nombre).select_related("rol").first()
        ahora = timezone.now()
        if usuario and usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
            minutos = max(1, math.ceil((usuario.bloqueado_hasta - ahora).total_seconds() / 60))
            form.add_error(None, f"Cuenta bloqueada por intentos fallidos. Intenta de nuevo en {minutos} min.")
            registrar(request, "login_fallido", "cuentas", usuario, "Intento de ingreso con cuenta bloqueada",
                      usuario=usuario)
        elif usuario and usuario.check_password(clave):
            if not usuario.is_active:
                form.add_error(None, "Tu cuenta está desactivada. Consulta con el dueño del negocio.")
                registrar(request, "login_fallido", "cuentas", usuario, "Intento de ingreso con cuenta desactivada",
                          usuario=usuario)
            else:
                usuario.intentos_fallidos = 0
                usuario.bloqueado_hasta = None
                usuario.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
                login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
                registrar(request, "login", "cuentas", usuario, "Inició sesión")
                destino = request.GET.get("next", "")
                if url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
                    return redirect(destino)
                return redirect(_destino_panel(usuario))
        else:
            if usuario:
                usuario.intentos_fallidos += 1
                if usuario.intentos_fallidos >= settings.MAX_INTENTOS_LOGIN:
                    usuario.bloqueado_hasta = ahora + timedelta(minutes=settings.MINUTOS_BLOQUEO_LOGIN)
                    usuario.intentos_fallidos = 0
                    registrar(request, "bloqueo", "cuentas", usuario,
                              "Cuenta bloqueada temporalmente por intentos fallidos", usuario=usuario)
                usuario.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
            registrar(request, "login_fallido", "cuentas", usuario,
                      "Usuario o contraseña incorrectos", usuario=usuario, usuario_nombre=nombre)
            form.add_error(None, "Usuario o contraseña incorrectos.")
    return render(request, "cuentas/login.html", {"form": form})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        registrar(request, "logout", "cuentas", request.user, "Cerró sesión")
    logout(request)
    return redirect("cuentas:login")


@login_required
@never_cache
def cambiar_password(request):
    """Pantalla obligatoria tras una contraseña temporal; también sirve desde Mi perfil."""
    form = CambiarPasswordForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        usuario.debe_cambiar_password = False
        usuario.save(update_fields=["debe_cambiar_password"])
        update_session_auth_hash(request, usuario)
        registrar(request, "cambiar_password", "cuentas", usuario, "Cambió su contraseña")
        messages.success(request, "Contraseña actualizada.")
        return redirect("nucleo:inicio")
    return render(request, "cuentas/cambiar_password.html",
                  {"form": form, "obligatorio": request.user.debe_cambiar_password})


@login_required
def perfil(request):
    form = PerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST":
        antes = valores(Usuario.objects.get(pk=request.user.pk), ["first_name", "last_name", "email", "telefono"])
        if form.is_valid():
            usuario = form.save()
            a, d = cambios(antes, valores(usuario, ["first_name", "last_name", "email", "telefono"]))
            if d:
                registrar(request, "editar", "cuentas", usuario, "Actualizó su perfil", a, d)
            messages.success(request, "Perfil actualizado.")
            return redirect("cuentas:perfil")
        messages.error(request, "Revisa los campos marcados.")
    return render(request, "cuentas/perfil.html", {"form": form})


# ---------------------------------------------------------------- Usuarios
@permiso_requerido("usuarios", "ver")
def usuarios(request):
    qs = Usuario.objects.select_related("rol")
    q = request.GET.get("q", "").strip()
    rol = request.GET.get("rol", "")
    estado = request.GET.get("estado", "")
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q)
            | Q(documento__icontains=q) | Q(email__icontains=q)
        )
    if rol.isdigit():
        qs = qs.filter(rol_id=int(rol))
    if estado == "activo":
        qs = qs.filter(is_active=True)
    elif estado == "inactivo":
        qs = qs.filter(is_active=False)
    pagina, parametros = paginar(request, qs)
    for u in pagina:  # qué filas puede gestionar quien consulta
        u.gestionable = servicios.puede_gestionar(request.user, u)
    return render(request, "cuentas/usuarios.html", {
        "pagina": pagina, "qs": parametros, "roles": Rol.objects.all(),
        "f": {"q": q, "rol": rol, "estado": estado},
    })


@permiso_requerido("usuarios", "crear")
@never_cache
def usuario_crear(request):
    form = UsuarioForm(request.POST or None, actor=request.user)
    if request.method == "POST":
        if form.is_valid():
            usuario = form.save(commit=False)
            clave = servicios.generar_password_temporal()
            usuario.set_password(clave)
            usuario.debe_cambiar_password = True
            usuario.creado_por = request.user
            usuario.save()
            registrar(request, "crear", "usuarios", usuario,
                      f"Registró al usuario {usuario.username} con el rol {usuario.rol}",
                      despues=valores(usuario, CAMPOS_USUARIO))
            return render(request, "cuentas/credenciales.html",
                          {"usuario": usuario, "clave": clave, "motivo": "creado"})
        messages.error(request, "Revisa los campos marcados.")
    return render(request, "cuentas/usuario_form.html", {"form": form, "editando": None})


@permiso_requerido("usuarios", "editar")
def usuario_editar(request, pk):
    usuario = get_object_or_404(Usuario.objects.select_related("rol"), pk=pk)
    if usuario.pk == request.user.pk:
        return redirect("cuentas:perfil")
    if not servicios.puede_gestionar(request.user, usuario):
        return denegar(request, "usuarios", "editar")
    antes = valores(usuario, CAMPOS_USUARIO)
    rol_anterior = usuario.rol
    form = UsuarioForm(request.POST or None, instance=usuario, actor=request.user)
    if request.method == "POST":
        if form.is_valid():
            nuevo_rol = form.cleaned_data["rol"]
            if rol_anterior and rol_anterior.es_dueno and nuevo_rol != rol_anterior \
                    and not servicios.quedan_duenos_activos(usuario):
                form.add_error("rol", "Debe quedar al menos un dueño activo en el sistema.")
            else:
                usuario = form.save()
                a, d = cambios(antes, valores(usuario, CAMPOS_USUARIO))
                if d:
                    registrar(request, "editar", "usuarios", usuario,
                              f"Editó al usuario {usuario.username}", a, d)
                    if "rol" in d:
                        servicios.cerrar_sesiones(usuario)  # el nuevo rol aplica desde el próximo ingreso
                messages.success(request, "Usuario actualizado.")
                return redirect("cuentas:usuarios")
        messages.error(request, "Revisa los campos marcados.")
    return render(request, "cuentas/usuario_form.html", {"form": form, "editando": usuario})


@require_POST
@permiso_requerido("usuarios", "desactivar")
def usuario_estado(request, pk):
    usuario = get_object_or_404(Usuario.objects.select_related("rol"), pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect("cuentas:usuarios")
    if not servicios.puede_gestionar(request.user, usuario):
        return denegar(request, "usuarios", "desactivar")
    if usuario.is_active:
        if usuario.es_dueno and not servicios.quedan_duenos_activos(usuario):
            messages.error(request, "Debe quedar al menos un dueño activo en el sistema.")
            return redirect("cuentas:usuarios")
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        servicios.cerrar_sesiones(usuario)
        registrar(request, "desactivar", "usuarios", usuario, f"Desactivó al usuario {usuario.username}",
                  {"is_active": True}, {"is_active": False})
        messages.success(request, f"{usuario.nombre_completo} fue desactivado y su sesión se cerró.")
    else:
        usuario.is_active = True
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.save(update_fields=["is_active", "intentos_fallidos", "bloqueado_hasta"])
        registrar(request, "activar", "usuarios", usuario, f"Activó al usuario {usuario.username}",
                  {"is_active": False}, {"is_active": True})
        messages.success(request, f"{usuario.nombre_completo} fue activado.")
    return redirect("cuentas:usuarios")


@require_POST
@permiso_requerido("usuarios", "autorizar")
@never_cache
def usuario_restablecer(request, pk):
    usuario = get_object_or_404(Usuario.objects.select_related("rol"), pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "Cambia tu propia contraseña desde Mi perfil.")
        return redirect("cuentas:usuarios")
    if not servicios.puede_gestionar(request.user, usuario):
        return denegar(request, "usuarios", "autorizar")
    clave = servicios.generar_password_temporal()
    usuario.set_password(clave)
    usuario.debe_cambiar_password = True
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.save(update_fields=["password", "debe_cambiar_password", "intentos_fallidos", "bloqueado_hasta"])
    servicios.cerrar_sesiones(usuario)
    registrar(request, "restablecer_password", "usuarios", usuario,
              f"Restableció la contraseña de {usuario.username}")
    return render(request, "cuentas/credenciales.html", {"usuario": usuario, "clave": clave, "motivo": "restablecido"})


# ------------------------------------------------------------------- Roles
@permiso_requerido("roles", "ver")
def roles(request):
    lista = Rol.objects.prefetch_related("permisos")
    filas = []
    for r in lista:
        visibles = permisos_visibles(r.codigo)
        total_rol = len(todos_los_permisos()) if visibles is None else len(visibles)
        filas.append({
            "rol": r,
            "usuarios": r.usuarios.filter(is_active=True).count(),
            "permisos": len(r.claves_permisos()),
            "total_permisos": total_rol,
            "editable": _rol_editable(request.user, r),
        })
    return render(request, "cuentas/roles.html", {"filas": filas})


def _rol_editable(actor, rol):
    """El rol de Dueño no se edita; nadie edita roles de nivel igual o superior al suyo."""
    if rol.es_dueno:
        return False
    return actor.es_dueno or rol.nivel < actor.nivel


@permiso_requerido("roles", "ver")
def rol_permisos(request, pk):
    rol = get_object_or_404(Rol, pk=pk)
    editable = _rol_editable(request.user, rol) and request.user.tiene_permiso("roles", "editar")
    propios = request.user.permisos_set()
    actuales = rol.claves_permisos()
    visibles = permisos_visibles(rol.codigo)
    if visibles is None:
        claves_visibles = {f"{modulo}.{accion}" for modulo, accion in todos_los_permisos()}
    else:
        claves_visibles = set(visibles)
    modulos = {
        modulo: [accion for accion in acciones if f"{modulo}.{accion}" in claves_visibles]
        for modulo, acciones in CATALOGO_PERMISOS.items()
    }
    modulos = {modulo: acciones for modulo, acciones in modulos.items() if acciones}
    acciones = [
        accion for accion in NOMBRES_ACCION
        if any(accion in lista for lista in modulos.values())
    ]
    # Permisos que el rol ya tuviera fuera de su alcance: se retiran al guardar.
    fuera_de_alcance = sorted(actuales - claves_visibles)

    if request.method == "POST":
        if not editable:
            return denegar(request, "roles", "editar")
        enviados = set(request.POST.getlist("permiso"))
        # Solo se pueden conceder o retirar permisos que el propio usuario posee.
        delegables = propios if not request.user.es_dueno else claves_visibles
        nuevos = ((enviados & claves_visibles) & delegables) | ((actuales & claves_visibles) - delegables)
        agregados, quitados = sorted(nuevos - actuales), sorted(actuales - nuevos)
        if agregados or quitados:
            rol.permisos.set([p for p in Permiso.objects.all() if p.clave in nuevos])
            registrar(request, "permisos", "roles", rol, f"Cambió los permisos del rol {rol.nombre}",
                      {"quitados": quitados}, {"agregados": agregados})
            messages.success(request, "Permisos actualizados. Aplican de inmediato a las nuevas peticiones.")
        else:
            messages.info(request, "No hubo cambios.")
        return redirect("cuentas:rol_permisos", pk=rol.pk)

    matriz = []
    for modulo, acciones_modulo in modulos.items():
        celdas = []
        for accion in acciones:
            if accion in acciones_modulo:
                clave = f"{modulo}.{accion}"
                celdas.append({
                    "clave": clave, "marcado": clave in actuales,
                    "habilitado": editable and (request.user.es_dueno or clave in propios),
                    "ayuda": AYUDA_ACCION.get((modulo, accion), ""),
                })
            else:
                celdas.append(None)
        matriz.append({"modulo": NOMBRES_MODULO[modulo], "celdas": celdas})
    return render(request, "cuentas/rol_permisos.html", {
        "rol": rol, "matriz": matriz, "acciones": [NOMBRES_ACCION[a] for a in acciones],
        "editable": editable, "fuera_de_alcance": fuera_de_alcance,
    })
