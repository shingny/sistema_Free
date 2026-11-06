from django.urls import NoReverseMatch, reverse

from .models import Configuracion


MENU_ADMIN = [
    ("Dashboard", "nucleo:dashboard", "dashboard.ver", "home", True),
    ("Cajas y turnos", "ventas:cajas", "caja.supervisar", "chart", False),
    ("Mesas", "ventas:mesas_lista", "mesas.gestionar", "table", False),
    ("Pedidos", "nucleo:pedidos_supervision", "dashboard.ver", "list", False),
    ("Usuarios", "cuentas:usuarios", "usuarios.ver", "users", False),
    ("Roles y permisos", "cuentas:roles", "roles.ver", "shield", False),
    ("Productos", "catalogo:productos", "productos.ver", "box", False),
    ("Categorías", "catalogo:categorias", "categorias.ver", "tag", False),
    ("Métodos de pago", "ventas:metodos_pago", "metodos_pago.ver", "cash", False),
    ("Productos agotados", "cocina:agotados", "cocina.ver", "box", False),
    ("Configuración", "nucleo:configuracion", "configuracion.ver", "gear", False),
]

MENU_COCINA = [
    ("Tablero de cocina", "cocina:tablero", "cocina.ver", "list", True),
    ("Historial", "cocina:historial", "cocina.ver", "clock", False),
    ("Productos agotados", "cocina:agotados", "cocina.ver", "box", False),
]

MENU_MESERO = [
    ("Inicio", "mesero:inicio", "mesas.ver", "home", True),
    ("Mesas", "mesero:mesas", "mesas.ver", "table", False),
    ("Pedidos activos", "mesero:pedidos_activos", "pedidos.ver", "list", False),
    ("Pedidos listos", "mesero:pedidos_listos", "pedidos.ver", "check", False),
    ("Historial", "mesero:historial", "pedidos.ver", "clock", False),
]

MENU_CAJA = [
    ("Inicio", "caja:inicio", "ventas.ver", "home", True),
    ("Nueva venta", "caja:nueva_venta", "ventas.crear", "cart", False),
    ("Mesas", "caja:mesas", "mesas.ver", "table", False),
    ("Pedidos", "caja:pedidos", "pedidos.ver", "list", False),
    ("Historial de ventas", "caja:historial", "ventas.ver", "clock", False),
    ("Apertura de caja", "caja:caja_abrir", "caja.abrir", "cash", False),
    ("Movimientos de caja", "caja:caja_movimientos", "caja.ver", "arrow-down", False),
    ("Cierre de caja", "caja:caja_cerrar", "caja.cerrar", "lock", False),
]


def _construir_menu(definicion, permisos, request):
    items = []
    for etiqueta, nombre_url, permiso, icono, exacto in definicion:
        if permiso not in permisos:
            continue
        try:
            url = reverse(nombre_url)
        except NoReverseMatch:
            continue
        activo = request.path == url if exacto else request.path.startswith(url)
        items.append({"etiqueta": etiqueta, "url": url, "icono": icono, "activo": activo})
    return items


def global_ctx(request):
    config = Configuracion.obtener()
    contexto = {
        "config": config,
        "permisos": set(),
        "menu": [],
        "menu_admin": [],
        "menu_caja": [],
        "menu_cocina": [],
        "menu_mesero": [],
        "panel_base": "base.html",
    }
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return contexto

    permisos = usuario.permisos_set()
    menu_admin = _construir_menu(MENU_ADMIN, permisos, request)
    menu_caja = _construir_menu(MENU_CAJA, permisos, request)
    menu_cocina = _construir_menu(MENU_COCINA, permisos, request)
    menu_mesero = _construir_menu(MENU_MESERO, permisos, request)
    resolver_match = getattr(request, "resolver_match", None)
    namespace = getattr(resolver_match, "namespace", "") if resolver_match else ""
    url_name = getattr(resolver_match, "url_name", "") if resolver_match else ""

    if "dashboard.ver" in permisos and namespace == "cocina" and url_name == "agotados":
        menu = menu_admin
        panel_base = "base_admin.html"
    elif namespace == "mesero":
        menu = menu_mesero
        panel_base = "base_mesero.html"
    elif namespace == "cocina":
        menu = menu_cocina
        panel_base = "base_cocina.html"
    elif namespace == "caja":
        menu = menu_caja
        panel_base = "base_caja.html"
    elif "dashboard.ver" in permisos:
        menu = menu_admin
        panel_base = "base_admin.html"
    elif "ventas.ver" in permisos or "caja.ver" in permisos:
        menu = menu_caja
        panel_base = "base_caja.html"
    elif "cocina.ver" in permisos and not "mesas.abrir" in permisos:
        menu = menu_cocina
        panel_base = "base_cocina.html"
    elif "mesas.ver" in permisos:
        menu = menu_mesero
        panel_base = "base_mesero.html"
    else:
        menu = []
        panel_base = "base.html"

    contexto.update({
        "permisos": permisos,
        "menu": menu,
        "menu_admin": menu_admin,
        "menu_caja": menu_caja,
        "menu_cocina": menu_cocina,
        "menu_mesero": menu_mesero,
        "panel_base": panel_base,
        "perfil_activo": request.path.startswith(reverse("cuentas:perfil")),
    })
    return contexto
