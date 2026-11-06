from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.cuentas.testing import CLAVE, crear_usuario, preparar_roles
from apps.nucleo.auditoria import registrar
from apps.nucleo.models import Auditoria, Configuracion
from apps.nucleo.validaciones import (
    validar_documento,
    validar_nombre,
    validar_nombre_comercial,
    validar_ruc,
    validar_solo_digitos,
    validar_telefono,
)


class AuditoriaInalterableTests(TestCase):
    def setUp(self):
        preparar_roles()
        self.reg = registrar(None, "crear", "prueba", descripcion="x")

    def test_no_se_puede_modificar(self):
        self.reg.descripcion = "otro"
        with self.assertRaises(PermissionError):
            self.reg.save()

    def test_no_se_puede_eliminar(self):
        with self.assertRaises(PermissionError):
            self.reg.delete()
        with self.assertRaises(PermissionError):
            Auditoria.objects.all().delete()
        with self.assertRaises(PermissionError):
            Auditoria.objects.all().update(descripcion="x")


class PanelTests(TestCase):
    def setUp(self):
        preparar_roles()
        self.dueno = crear_usuario("duenio", "dueno")
        self.cajero = crear_usuario("cajero1", "cajero")

    def test_dashboard_muestra_datos_reales_y_ventas(self):
        self.client.force_login(self.dueno)
        r = self.client.get(reverse("nucleo:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["usuarios_activos"], 2)
        self.assertEqual(r.context["productos_activos"], 0)
        self.assertTrue(r.context["puede_ventas"])
        self.assertEqual(r.context["operaciones"], 0)
        self.assertContains(r, "Ventas del periodo")
        self.assertContains(r, "Cajas abiertas")

    def test_cajero_no_ve_dashboard(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("nucleo:dashboard")).status_code, 403)
        r = self.client.get(reverse("nucleo:inicio"))
        self.assertRedirects(r, reverse("caja:inicio"), fetch_redirect_response=False)

    def test_guardar_configuracion_persiste(self):
        self.client.force_login(self.dueno)
        r = self.client.post(reverse("nucleo:configuracion"), {
            "nombre_comercial": "Pollería El Sabor", "razon_social": "", "ruc": "20123456789",
            "direccion": "Av. Real 123, Huancayo", "telefono": "064 123456", "correo": "", "horario_atencion": "",
        })
        self.assertEqual(r.status_code, 302)
        c = Configuracion.obtener()
        self.assertEqual(c.nombre_comercial, "Pollería El Sabor")
        self.assertEqual(c.moneda, "PEN")
        self.assertTrue(Auditoria.objects.filter(modulo="configuracion", accion="editar").exists())

    def test_ruc_invalido(self):
        self.client.force_login(self.dueno)
        r = self.client.post(reverse("nucleo:configuracion"), {"nombre_comercial": "X", "ruc": "123"})
        self.assertContains(r, "11 dígitos")

    def test_cajero_no_edita_configuracion(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.post(reverse("nucleo:configuracion"), {"nombre_comercial": "Hack"}).status_code, 403)

    def test_actividad_y_exportacion(self):
        self.client.force_login(self.dueno)
        self.assertEqual(self.client.get(reverse("nucleo:actividad")).status_code, 200)
        self.assertEqual(self.client.get(reverse("nucleo:actividad_exportar")).status_code, 200)
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("nucleo:actividad")).status_code, 403)

class SupervisionPedidosTests(TestCase):
    def setUp(self):
        preparar_roles()
        self.dueno = crear_usuario("dueno_sup", "dueno")
        self.client.force_login(self.dueno)

    def test_supervision_view(self):
        r = self.client.get(reverse("nucleo:pedidos_supervision"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("pagina", r.context)

    def test_supervision_filtros(self):
        r = self.client.get(reverse("nucleo:pedidos_supervision"), {"estado": "pendiente", "origen": "salon"})
        self.assertEqual(r.status_code, 200)

class MeseroRedirectTests(TestCase):
    def setUp(self):
        preparar_roles()
        self.mesero = crear_usuario("mesero_redirect", "mesero")

    def test_login_mesero_redirige(self):
        respuesta = self.client.post(
            reverse("cuentas:login"),
            {"username": self.mesero.username, "password": CLAVE},
        )
        self.assertRedirects(respuesta, reverse("mesero:inicio"), fetch_redirect_response=False)


class AccesoEntrePanelesTests(TestCase):
    """Verifica que cada rol solo accede a su propio panel y recibe 403
    al intentar entrar a URLs de otros paneles (click en boton/fila)."""

    def setUp(self):
        preparar_roles()
        self.dueno = crear_usuario("dueno_ae", "dueno")
        self.cajero = crear_usuario("cajero_ae", "cajero")
        self.mesero = crear_usuario("mesero_ae", "mesero")
        self.cocinero = crear_usuario("cocina_ae", "cocinero")
        self.jefe_cocina = crear_usuario("jefe_ae", "jefe_cocina")

    # ------------------------------------------------------------------
    # Login: cada rol redirige a su propio panel
    # ------------------------------------------------------------------
    def test_login_dueno_redirige_panel_admin(self):
        r = self.client.post(
            reverse("cuentas:login"),
            {"username": self.dueno.username, "password": CLAVE},
        )
        self.assertRedirects(r, reverse("nucleo:dashboard"), fetch_redirect_response=False)

    def test_login_cajero_redirige_panel_caja(self):
        r = self.client.post(
            reverse("cuentas:login"),
            {"username": self.cajero.username, "password": CLAVE},
        )
        self.assertRedirects(r, reverse("caja:inicio"), fetch_redirect_response=False)

    def test_login_mesero_redirige_panel_mesero(self):
        r = self.client.post(
            reverse("cuentas:login"),
            {"username": self.mesero.username, "password": CLAVE},
        )
        self.assertRedirects(r, reverse("mesero:inicio"), fetch_redirect_response=False)

    def test_login_cocinero_redirige_panel_cocina(self):
        r = self.client.post(
            reverse("cuentas:login"),
            {"username": self.cocinero.username, "password": CLAVE},
        )
        self.assertRedirects(r, reverse("cocina:tablero"), fetch_redirect_response=False)

    def test_login_jefe_cocina_redirige_panel_cocina(self):
        r = self.client.post(
            reverse("cuentas:login"),
            {"username": self.jefe_cocina.username, "password": CLAVE},
        )
        self.assertRedirects(r, reverse("cocina:tablero"), fetch_redirect_response=False)

    # ------------------------------------------------------------------
    # Dueno y administrador: acceso total (no bloqueados)
    # ------------------------------------------------------------------
    def test_dueno_accede_a_todos_los_paneles(self):
        self.client.force_login(self.dueno)
        urls = [
            reverse("nucleo:dashboard"),
            reverse("caja:inicio"),
            reverse("cocina:tablero"),
            reverse("mesero:inicio"),
            reverse("ventas:inicio"),
            reverse("cuentas:usuarios"),
            reverse("catalogo:productos"),
        ]
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, f"Dueño bloqueado en {url}")

    # ------------------------------------------------------------------
    # Cajero: solo caja y ventas relacionadas; no cocina, admin, mesero-crear
    # ------------------------------------------------------------------
    def test_cajero_no_accede_panel_admin(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("nucleo:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)
        self.assertEqual(self.client.get(reverse("nucleo:actividad")).status_code, 403)
        self.assertEqual(self.client.get(reverse("nucleo:configuracion")).status_code, 403)

    def test_cajero_no_accede_panel_cocina(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("cocina:tablero")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cocina:historial")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cocina:agotados")).status_code, 403)

    def test_cajero_no_puede_abrir_cerrar_mesas(self):
        self.client.force_login(self.cajero)
        # Cajero tiene mesas.ver (ver mesas) pero NO mesas.abrir ni mesas.cerrar.
        self.assertEqual(self.client.post(reverse("mesero:mesa_abrir", args=[1])).status_code, 403)
        self.assertEqual(self.client.post(reverse("mesero:cuenta_cerrar", args=[1])).status_code, 403)

    def test_cajero_no_accede_supervision_cajas(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("ventas:cajas")).status_code, 403)

    def test_cajero_accede_su_propio_panel_caja(self):
        self.client.force_login(self.cajero)
        r = self.client.get(reverse("caja:inicio"))
        self.assertEqual(r.status_code, 200)

    # ------------------------------------------------------------------
    # Mesero: solo mesas, pedidos propios, cocina.ver (solo lectura)
    # NO puede: caja, admin, crear ventas, reportar agotado
    # ------------------------------------------------------------------
    def test_mesero_no_accede_panel_caja(self):
        self.client.force_login(self.mesero)
        self.assertEqual(self.client.get(reverse("caja:inicio")).status_code, 403)
        self.assertEqual(self.client.get(reverse("caja:nueva_venta")).status_code, 403)
        self.assertEqual(self.client.get(reverse("caja:caja_abrir")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ventas:cajas")).status_code, 403)

    def test_mesero_no_accede_panel_admin(self):
        self.client.force_login(self.mesero)
        self.assertEqual(self.client.get(reverse("nucleo:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)
        self.assertEqual(self.client.get(reverse("nucleo:actividad")).status_code, 403)

    def test_mesero_no_puede_reportar_agotado(self):
        self.client.force_login(self.mesero)
        r = self.client.post(reverse("cocina:reportar_agotado"), {"producto": 1})
        self.assertEqual(r.status_code, 403)

    def test_mesero_no_puede_crear_venta(self):
        self.client.force_login(self.mesero)
        self.assertEqual(self.client.get(reverse("ventas:inicio")).status_code, 403)
        self.assertEqual(self.client.get(reverse("caja:nueva_venta")).status_code, 403)

    def test_mesero_accede_su_propio_panel(self):
        self.client.force_login(self.mesero)
        r = self.client.get(reverse("mesero:inicio"))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("mesero:mesas"))
        self.assertEqual(r.status_code, 200)

    # Mesero SÍ tiene cocina.ver, puede ver tablero (solo lectura)
    def test_mesero_ve_tablero_cocina_solo_lectura(self):
        self.client.force_login(self.mesero)
        self.assertEqual(self.client.get(reverse("cocina:tablero")).status_code, 200)
        self.assertEqual(self.client.get(reverse("cocina:historial")).status_code, 200)
        self.assertEqual(self.client.get(reverse("cocina:agotados")).status_code, 200)

    # ------------------------------------------------------------------
    # Cocinero / Jefe cocina: solo cocina, pedidos.ver, productos.ver
    # NO puede: caja, admin, mesas.abrir/cerrar, ventas.crear
    # ------------------------------------------------------------------
    def test_cocinero_no_accede_panel_caja(self):
        self.client.force_login(self.cocinero)
        self.assertEqual(self.client.get(reverse("caja:inicio")).status_code, 403)
        self.assertEqual(self.client.get(reverse("caja:nueva_venta")).status_code, 403)
        self.assertEqual(self.client.get(reverse("caja:caja_abrir")).status_code, 403)

    def test_cocinero_no_accede_panel_admin(self):
        self.client.force_login(self.cocinero)
        self.assertEqual(self.client.get(reverse("nucleo:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)
        self.assertEqual(self.client.get(reverse("nucleo:actividad")).status_code, 403)

    def test_cocinero_no_puede_abrir_cerrar_mesas(self):
        self.client.force_login(self.cocinero)
        # Cocinero tiene mesas.ver? NO. Tiene pedidos.ver, cocina.*, productos.ver, categorias.ver
        self.assertEqual(self.client.get(reverse("mesero:inicio")).status_code, 403)

    def test_cocinero_accede_su_propio_panel_cocina(self):
        self.client.force_login(self.cocinero)
        r = self.client.get(reverse("cocina:tablero"))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("cocina:historial"))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse("cocina:agotados"))
        self.assertEqual(r.status_code, 200)

    def test_jefe_cocina_no_accede_panel_caja(self):
        self.client.force_login(self.jefe_cocina)
        self.assertEqual(self.client.get(reverse("caja:inicio")).status_code, 403)
        self.assertEqual(self.client.get(reverse("caja:nueva_venta")).status_code, 403)

    def test_jefe_cocina_no_accede_panel_admin(self):
        self.client.force_login(self.jefe_cocina)
        self.assertEqual(self.client.get(reverse("nucleo:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)


class ValidacionesTests(TestCase):
    """Reglas de entrada reutilizables (nombres, documentos, teléfonos, números)."""

    def test_nombre_acepta_letras_y_separadores(self):
        self.assertEqual(validar_nombre("  Ana   María "), "Ana María")
        self.assertEqual(validar_nombre("O'Brien"), "O'Brien")
        self.assertEqual(validar_nombre("Jean-Pierre"), "Jean-Pierre")

    def test_nombre_rechaza_numeros_y_simbolos(self):
        for valor in ["Ana123", "Ana@casa", "A1", "12345"]:
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                validar_nombre(valor)

    def test_nombre_comercial_acepta_numeros_y_signos(self):
        self.assertEqual(validar_nombre_comercial("Pollo a la brasa 1/4"), "Pollo a la brasa 1/4")
        self.assertEqual(validar_nombre_comercial("Combos & Promos"), "Combos & Promos")

    def test_nombre_comercial_rechaza_caracteres_peligrosos(self):
        for valor in ["Pollo <script>", "Promo #1", "A"]:
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                validar_nombre_comercial(valor)

    def test_documento(self):
        self.assertEqual(validar_documento("12345678"), "12345678")
        self.assertEqual(validar_documento(""), "")
        with self.assertRaises(ValidationError):
            validar_documento("123")

    def test_telefono(self):
        self.assertEqual(validar_telefono("064 123456"), "064 123456")
        self.assertEqual(validar_telefono(""), "")
        with self.assertRaises(ValidationError):
            validar_telefono("hola")

    def test_ruc_y_solo_digitos(self):
        self.assertEqual(validar_ruc("20123456789"), "20123456789")
        with self.assertRaises(ValidationError):
            validar_ruc("123")
        self.assertEqual(validar_solo_digitos("12345678"), "12345678")
        with self.assertRaises(ValidationError):
            validar_solo_digitos("1234abc")
