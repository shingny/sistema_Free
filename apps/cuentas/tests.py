from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import Permiso, Rol, Usuario
from apps.cuentas.testing import CLAVE, crear_usuario, preparar_roles
from apps.nucleo.models import Auditoria


class BaseCuentas(TestCase):
    def setUp(self):
        preparar_roles()
        self.dueno = crear_usuario("duenio", "dueno")
        self.admin = crear_usuario("admin1", "administrador")
        self.cajero = crear_usuario("cajero1", "cajero")

    def datos_usuario(self, **cambios):
        datos = {"first_name": "Ana", "last_name": "Pérez", "documento": "12345678", "username": "ana.perez",
                 "email": "", "telefono": "", "rol": Rol.objects.get(codigo="mesero").pk}
        datos.update(cambios)
        return datos


class InicioSesionTests(BaseCuentas):
    def test_login_correcto_y_auditado(self):
        r = self.client.post(reverse("cuentas:login"), {"username": "duenio", "password": CLAVE})
        self.assertRedirects(r, reverse("nucleo:dashboard"), fetch_redirect_response=False)
        self.assertTrue(Auditoria.objects.filter(accion="login", usuario=self.dueno).exists())

    def test_login_cajero_redirige_a_caja(self):
        r = self.client.post(reverse("cuentas:login"), {"username": "cajero1", "password": CLAVE})
        self.assertRedirects(r, reverse("caja:inicio"), fetch_redirect_response=False)

    def test_clave_incorrecta(self):
        r = self.client.post(reverse("cuentas:login"), {"username": "duenio", "password": "mala"})
        self.assertContains(r, "Usuario o contraseña incorrectos")
        self.assertTrue(Auditoria.objects.filter(accion="login_fallido").exists())

    def test_bloqueo_tras_intentos_fallidos(self):
        for _ in range(5):
            self.client.post(reverse("cuentas:login"), {"username": "cajero1", "password": "mala"})
        r = self.client.post(reverse("cuentas:login"), {"username": "cajero1", "password": CLAVE})
        self.assertContains(r, "bloqueada")

    def test_usuario_inactivo_no_ingresa(self):
        self.cajero.is_active = False
        self.cajero.save()
        r = self.client.post(reverse("cuentas:login"), {"username": "cajero1", "password": CLAVE})
        self.assertContains(r, "desactivada")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_contrasena_guardada_con_hash(self):
        self.assertNotEqual(self.dueno.password, CLAVE)
        self.assertTrue(self.dueno.password.startswith("argon2"))


class PermisosBackendTests(BaseCuentas):
    def test_cajero_recibe_403_en_usuarios(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("cuentas:usuarios")).status_code, 403)
        self.assertTrue(Auditoria.objects.filter(accion="acceso_denegado", usuario=self.cajero).exists())

    def test_cajero_no_puede_crear_usuarios_aunque_envie_el_post(self):
        self.client.force_login(self.cajero)
        r = self.client.post(reverse("cuentas:usuario_crear"), self.datos_usuario())
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Usuario.objects.filter(username="ana.perez").exists())

    def test_sin_sesion_redirige_a_login(self):
        r = self.client.get(reverse("cuentas:usuarios"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("cuentas:login"), r.url)

    def test_menu_solo_muestra_modulos_autorizados(self):
        self.client.force_login(self.cajero)
        r = self.client.get(reverse("caja:inicio"))
        self.assertContains(r, "panel-caja")
        self.assertNotContains(r, reverse("cuentas:usuarios"))


class UsuariosTests(BaseCuentas):
    def test_dueno_crea_usuario_con_clave_temporal(self):
        self.client.force_login(self.dueno)
        r = self.client.post(reverse("cuentas:usuario_crear"), self.datos_usuario())
        self.assertEqual(r.status_code, 200)
        u = Usuario.objects.get(username="ana.perez")
        self.assertTrue(u.debe_cambiar_password)
        self.assertTrue(u.password.startswith("argon2"))
        self.assertEqual(u.creado_por, self.dueno)
        self.assertTrue(Auditoria.objects.filter(accion="crear", modulo="usuarios").exists())
        self.assertNotIn("password", str(Auditoria.objects.filter(accion="crear").first().despues))

    def test_administrador_no_puede_asignar_rol_dueno_ni_administrador(self):
        self.client.force_login(self.admin)
        for codigo in ("dueno", "administrador"):
            r = self.client.post(reverse("cuentas:usuario_crear"),
                                 self.datos_usuario(rol=Rol.objects.get(codigo=codigo).pk))
            self.assertEqual(r.status_code, 200)  # vuelve al formulario con error
            self.assertFalse(Usuario.objects.filter(username="ana.perez").exists())

    def test_administrador_puede_crear_mesero(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("cuentas:usuario_crear"), self.datos_usuario())
        self.assertTrue(Usuario.objects.filter(username="ana.perez", rol__codigo="mesero").exists())

    def test_administrador_no_puede_editar_al_dueno(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("cuentas:usuario_editar", args=[self.dueno.pk]))
        self.assertEqual(r.status_code, 403)

    def test_usuario_duplicado_rechazado(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse("cuentas:usuario_crear"), self.datos_usuario())
        r = self.client.post(reverse("cuentas:usuario_crear"), self.datos_usuario(documento="87654321"))
        self.assertContains(r, "ya está en uso")

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse("cuentas:usuario_estado", args=[self.dueno.pk]))
        self.dueno.refresh_from_db()
        self.assertTrue(self.dueno.is_active)

    def test_desactivar_y_activar_con_auditoria(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse("cuentas:usuario_estado", args=[self.cajero.pk]))
        self.cajero.refresh_from_db()
        self.assertFalse(self.cajero.is_active)
        self.client.post(reverse("cuentas:usuario_estado", args=[self.cajero.pk]))
        self.cajero.refresh_from_db()
        self.assertTrue(self.cajero.is_active)
        self.assertEqual(Auditoria.objects.filter(modulo="usuarios", accion__in=["activar", "desactivar"]).count(), 2)

    def test_desactivar_cierra_la_sesion_del_usuario(self):
        from django.test import Client
        otro = Client()
        otro.force_login(self.cajero)
        self.assertEqual(otro.get(reverse("caja:inicio")).status_code, 200)
        self.client.force_login(self.dueno)
        self.client.post(reverse("cuentas:usuario_estado", args=[self.cajero.pk]))
        self.assertEqual(otro.get(reverse("caja:inicio")).status_code, 302)

    def test_restablecer_contrasena(self):
        self.client.force_login(self.dueno)
        r = self.client.post(reverse("cuentas:usuario_restablecer", args=[self.cajero.pk]))
        self.assertEqual(r.status_code, 200)
        self.cajero.refresh_from_db()
        self.assertTrue(self.cajero.debe_cambiar_password)
        self.assertFalse(self.cajero.check_password(CLAVE))
        self.assertTrue(Auditoria.objects.filter(accion="restablecer_password").exists())

    def test_administrador_sin_permiso_autorizar_no_restablece(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("cuentas:usuario_restablecer", args=[self.cajero.pk]))
        self.assertEqual(r.status_code, 403)

    def test_busqueda_y_filtros(self):
        self.client.force_login(self.dueno)
        r = self.client.get(reverse("cuentas:usuarios"), {"q": "cajero1", "estado": "activo"})
        self.assertContains(r, "cajero1")
        self.assertNotContains(r, "admin1")


class ClaveTemporalTests(BaseCuentas):
    def test_clave_temporal_obliga_a_cambiarla(self):
        self.cajero.debe_cambiar_password = True
        self.cajero.save()
        self.client.force_login(self.cajero)
        r = self.client.get(reverse("nucleo:inicio"))
        self.assertRedirects(r, reverse("cuentas:cambiar_password"), fetch_redirect_response=False)
        r = self.client.post(reverse("cuentas:cambiar_password"), {
            "old_password": CLAVE, "new_password1": "Nueva-Clave-9988", "new_password2": "Nueva-Clave-9988"})
        self.assertEqual(r.status_code, 302)
        self.cajero.refresh_from_db()
        self.assertFalse(self.cajero.debe_cambiar_password)
        self.assertEqual(self.client.get(reverse("caja:inicio")).status_code, 200)

    def test_no_acepta_la_misma_clave(self):
        self.client.force_login(self.cajero)
        r = self.client.post(reverse("cuentas:cambiar_password"), {
            "old_password": CLAVE, "new_password1": CLAVE, "new_password2": CLAVE})
        self.assertContains(r, "distinta de la actual")


class RolesPermisosTests(BaseCuentas):
    def url(self, rol):
        return reverse("cuentas:rol_permisos", args=[Rol.objects.get(codigo=rol).pk])

    def otorgar(self, rol, *claves):
        for clave in claves:
            m, a = clave.split(".")
            Rol.objects.get(codigo=rol).permisos.add(Permiso.objects.get(modulo=m, accion=a))

    def test_dueno_configura_permisos_de_cajero(self):
        self.client.force_login(self.dueno)
        self.client.post(self.url("cajero"), {"permiso": ["productos.ver", "ventas.crear"]})
        claves = Rol.objects.get(codigo="cajero").claves_permisos()
        self.assertEqual(claves, {"productos.ver", "ventas.crear"})
        self.assertTrue(Auditoria.objects.filter(accion="permisos").exists())

    def test_rol_dueno_no_se_modifica(self):
        self.client.force_login(self.dueno)
        r = self.client.post(self.url("dueno"), {"permiso": []})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Usuario.objects.get(pk=self.dueno.pk).tiene_permiso("usuarios", "crear"))

    def test_administrador_no_puede_concederse_ni_conceder_lo_que_no_tiene(self):
        self.otorgar("administrador", "roles.editar")
        self.client.force_login(Usuario.objects.get(pk=self.admin.pk))
        # No puede tocar su propio rol (nivel igual)
        self.assertEqual(self.client.post(self.url("administrador"), {"permiso": ["usuarios.autorizar"]}).status_code, 403)
        # Sobre un rol inferior solo puede conceder permisos que posee
        self.client.post(self.url("cajero"), {"permiso": ["productos.ver", "usuarios.autorizar", "configuracion.editar"]})
        claves = Rol.objects.get(codigo="cajero").claves_permisos()
        self.assertIn("productos.ver", claves)
        self.assertNotIn("usuarios.autorizar", claves)
        self.assertNotIn("configuracion.editar", claves)

    def test_administrador_no_puede_editar_rol_jefe_de_cocina_superior_a_cajero_pero_inferior_a_el(self):
        # jefe_cocina (nivel 50) es inferior al administrador (80): sí puede, si tiene roles.editar
        self.otorgar("administrador", "roles.editar")
        self.client.force_login(Usuario.objects.get(pk=self.admin.pk))
        r = self.client.post(self.url("jefe_cocina"), {"permiso": ["productos.ver"]})
        self.assertEqual(r.status_code, 302)

    def test_cambio_de_permisos_aplica_de_inmediato(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("catalogo:productos")).status_code, 200)
        Rol.objects.get(codigo="cajero").permisos.clear()
        self.assertEqual(self.client.get(reverse("catalogo:productos")).status_code, 403)

    # ------------------------------------------- permisos según el rol
    def test_mesero_solo_ve_sus_permisos(self):
        self.client.force_login(self.dueno)
        r = self.client.get(self.url("mesero"))
        for clave in ("mesas.ver", "mesas.abrir", "mesas.cerrar", "pedidos.ver",
                      "pedidos.editar", "pedidos.cancelar", "cocina.ver",
                      "productos.ver", "categorias.ver"):
            self.assertContains(r, f'value="{clave}"')
        for clave in ("productos.crear", "productos.editar", "productos.desactivar",
                      "productos.reportes", "categorias.crear", "pedidos.autorizar_cancelacion",
                      "cocina.actualizar", "cocina.ver_historial", "mesas.gestionar",
                      "dashboard.ver", "usuarios.ver", "roles.editar", "pagos.ver",
                      "caja.ver", "ventas.ver", "configuracion.ver", "auditoria.ver",
                      "metodos_pago.ver"):
            self.assertNotContains(r, f'value="{clave}"')

    def test_cajero_solo_ve_sus_permisos(self):
        self.client.force_login(self.dueno)
        r = self.client.get(self.url("cajero"))
        for clave in ("ventas.ver", "ventas.crear", "pagos.registrar", "caja.ver",
                      "caja.abrir", "caja.cerrar", "pedidos.ver", "pedidos.editar", "mesas.ver"):
            self.assertContains(r, f'value="{clave}"')
        for clave in ("ventas.anular", "ventas.descuento", "ventas.reportes",
                      "pagos.verificar", "pagos.reembolsar", "caja.supervisar",
                      "pedidos.cancelar", "pedidos.autorizar_cancelacion",
                      "productos.crear", "dashboard.ver", "usuarios.ver", "roles.editar",
                      "configuracion.ver", "auditoria.ver", "metodos_pago.ver"):
            self.assertNotContains(r, f'value="{clave}"')

    def test_cocinero_solo_ve_sus_permisos(self):
        self.client.force_login(self.dueno)
        r = self.client.get(self.url("cocinero"))
        for clave in ("cocina.ver", "cocina.actualizar", "cocina.reportar_agotado",
                      "cocina.registrar_incidencia", "cocina.ver_historial",
                      "pedidos.ver", "productos.ver", "categorias.ver"):
            self.assertContains(r, f'value="{clave}"')
        for clave in ("pedidos.editar", "pedidos.cancelar", "mesas.ver", "caja.ver",
                      "pagos.ver", "ventas.ver", "usuarios.ver", "productos.crear"):
            self.assertNotContains(r, f'value="{clave}"')

    def test_jefe_cocina_solo_ve_sus_permisos(self):
        self.client.force_login(self.dueno)
        r = self.client.get(self.url("jefe_cocina"))
        for clave in ("cocina.ver", "cocina.actualizar", "pedidos.ver", "mesas.ver", "productos.ver"):
            self.assertContains(r, f'value="{clave}"')
        for clave in ("mesas.gestionar", "pedidos.editar", "pedidos.cancelar",
                      "caja.ver", "pagos.ver", "ventas.ver", "productos.crear"):
            self.assertNotContains(r, f'value="{clave}"')

    def test_administrador_conserva_todos_los_permisos(self):
        self.client.force_login(self.dueno)
        r = self.client.get(self.url("administrador"))
        for clave in ("dashboard.ver", "usuarios.ver", "usuarios.autorizar",
                      "configuracion.editar", "pagos.registrar", "caja.ver", "mesas.gestionar"):
            self.assertContains(r, f'value="{clave}"')

    def test_no_otorga_permiso_fuera_del_alcance_del_rol(self):
        self.client.force_login(self.dueno)
        self.client.post(self.url("mesero"), {"permiso": ["pedidos.ver", "caja.ver"]})
        claves = Rol.objects.get(codigo="mesero").claves_permisos()
        self.assertIn("pedidos.ver", claves)
        self.assertNotIn("caja.ver", claves)

    def test_no_otorga_accion_no_permitida_dentro_de_un_modulo(self):
        self.client.force_login(self.dueno)
        self.client.post(self.url("mesero"), {"permiso": ["productos.ver", "productos.crear"]})
        claves = Rol.objects.get(codigo="mesero").claves_permisos()
        self.assertIn("productos.ver", claves)
        self.assertNotIn("productos.crear", claves)

    def test_avisa_permisos_fuera_de_alcance(self):
        rol = Rol.objects.get(codigo="mesero")
        rol.permisos.add(Permiso.objects.get(modulo="caja", accion="ver"))
        self.client.force_login(self.dueno)
        r = self.client.get(self.url("mesero"))
        self.assertContains(r, "no corresponden a su función")
        self.assertContains(r, "caja.ver")

    def test_guardar_retira_permisos_fuera_de_alcance(self):
        rol = Rol.objects.get(codigo="mesero")
        rol.permisos.add(Permiso.objects.get(modulo="caja", accion="ver"))
        self.client.force_login(self.dueno)
        self.client.post(self.url("mesero"), {"permiso": ["pedidos.ver"]})
        claves = Rol.objects.get(codigo="mesero").claves_permisos()
        self.assertNotIn("caja.ver", claves)


class ValidacionUsuarioTests(BaseCuentas):
    """El formulario de usuarios valida nombre, documento y teléfono."""

    def test_rechaza_nombres_con_numeros(self):
        self.client.force_login(self.dueno)
        r = self.client.post(reverse("cuentas:usuario_crear"), self.datos_usuario(first_name="Ana2"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.filter(username="ana.perez").exists())
        self.assertContains(r, "solo puede contener letras")

    def test_rechaza_documento_corto(self):
        self.client.force_login(self.dueno)
        r = self.client.post(reverse("cuentas:usuario_crear"), self.datos_usuario(documento="123"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.filter(username="ana.perez").exists())
        self.assertContains(r, "8 y 12")

    def test_rechaza_telefono_invalido(self):
        self.client.force_login(self.dueno)
        r = self.client.post(reverse("cuentas:usuario_crear"), self.datos_usuario(telefono="abc"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Usuario.objects.filter(username="ana.perez").exists())
        self.assertContains(r, "teléfono válido")

    def test_formulario_incluye_validacion_del_navegador(self):
        self.client.force_login(self.dueno)
        r = self.client.get(reverse("cuentas:usuario_crear"))
        self.assertContains(r, "pattern=")
        self.assertNotContains(r, "novalidate")
