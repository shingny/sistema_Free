import json
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.catalogo.models import Categoria, Producto
from apps.cuentas.testing import crear_usuario, preparar_roles
from apps.nucleo.models import Auditoria
from apps.ventas import services
from apps.ventas.models import Caja, CuentaMesa, Mesa, MetodoPago, Pago, Pedido, TurnoCaja, Venta


class BaseVentasTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        preparar_roles()
        cls.dueno = crear_usuario("dueno_ventas", "dueno")
        cls.admin = crear_usuario("admin_ventas", "administrador")
        cls.cajero = crear_usuario("cajero_ventas", "cajero")
        cls.otro_cajero = crear_usuario("cajero_dos_ventas", "cajero")
        cls.categoria = Categoria.objects.create(nombre="Pollos de prueba", orden=1)
        cls.producto = Producto.objects.create(
            nombre="Pollo entero de prueba", categoria=cls.categoria, precio=Decimal("30.00")
        )
        cls.caja, _ = Caja.objects.get_or_create(
            codigo="CAJA-01", defaults={"nombre": "Caja principal"}
        )
        cls.caja2, _ = Caja.objects.get_or_create(
            codigo="CAJA-02", defaults={"nombre": "Caja secundaria de prueba"}
        )
        cls.efectivo, _ = MetodoPago.objects.get_or_create(
            codigo="efectivo", defaults={"nombre": "Efectivo", "afecta_efectivo": True, "orden": 1}
        )
        cls.tarjeta, _ = MetodoPago.objects.get_or_create(
            codigo="tarjeta", defaults={"nombre": "Tarjeta", "orden": 2}
        )
        cls.transferencia, _ = MetodoPago.objects.get_or_create(
            codigo="transferencia",
            defaults={"nombre": "Transferencia", "requiere_verificacion": True, "orden": 3},
        )

    def abrir_turno(self, usuario=None, caja=None, monto="100.00"):
        return services.abrir_caja(usuario or self.cajero, caja or self.caja, Decimal(monto))

    def crear_venta(self, usuario=None, turno=None, items=None, metodo=None,
                    monto=Decimal("30.00"), **kwargs):
        usuario = usuario or self.cajero
        turno = turno or self.abrir_turno(usuario=usuario)
        if items is None:
            items = [{"producto_id": self.producto.pk, "cantidad": 1}]
        return services.crear_venta(
            usuario, turno, items, token=uuid.uuid4(), pago_metodo=metodo or self.efectivo,
            pago_monto=monto, **kwargs,
        )


class CajaTests(BaseVentasTestCase):
    def test_apertura_crea_movimiento_y_no_permite_duplicados(self):
        self.client.force_login(self.cajero)
        respuesta = self.client.post(reverse("ventas:caja_abrir"), {
            "caja": self.caja.pk, "monto_inicial": "100.00", "observacion": "Turno de prueba",
        })
        self.assertEqual(respuesta.status_code, 302)
        turno = TurnoCaja.objects.get(usuario=self.cajero, estado="abierta")
        self.assertEqual(turno.movimientos.count(), 1)
        self.assertEqual(turno.movimientos.first().tipo, "apertura")
        self.assertEqual(turno.efectivo_calculado(), Decimal("100.00"))

        # Un segundo POST no debe crear otro turno abierto.
        self.client.post(reverse("ventas:caja_abrir"), {
            "caja": self.caja.pk, "monto_inicial": "50.00",
        })
        self.assertEqual(TurnoCaja.objects.filter(usuario=self.cajero, estado="abierta").count(), 1)

    def test_cierre_calcula_efectivo_esperado_y_diferencia(self):
        turno = self.abrir_turno(monto="100.00")
        self.crear_venta(turno=turno, monto=Decimal("30.00"))
        services.registrar_movimiento(turno, self.cajero, "ingreso", Decimal("20.00"), "Propina")
        services.registrar_movimiento(turno, self.cajero, "egreso", Decimal("10.00"), "Compra")
        turno.refresh_from_db()
        self.assertEqual(turno.efectivo_calculado(), Decimal("140.00"))

        services.cerrar_caja(turno, self.cajero, Decimal("140.00"), "Cuadra")
        self.assertEqual(turno.estado, "cerrada")
        self.assertEqual(turno.efectivo_esperado, Decimal("140.00"))
        self.assertEqual(turno.diferencia, Decimal("0.00"))

    def test_cierre_con_faltante(self):
        turno = self.abrir_turno(monto="100.00")
        services.cerrar_caja(turno, self.cajero, Decimal("95.00"), "Faltante")
        self.assertEqual(turno.diferencia, Decimal("-5.00"))


class VentaTests(BaseVentasTestCase):
    def test_venta_en_efectivo_completa(self):
        self.abrir_turno()
        self.client.force_login(self.cajero)
        respuesta = self.client.post(reverse("ventas:nueva_venta"), {
            "items": json.dumps([{"producto_id": self.producto.pk, "cantidad": 2}]),
            "token": str(uuid.uuid4()),
            "metodo": self.efectivo.pk,
            "monto": "60.00",
            "cliente_nombre": "Ana Pérez",
        })
        self.assertEqual(respuesta.status_code, 302)
        venta = Venta.objects.get()
        self.assertEqual(venta.total, Decimal("60.00"))
        self.assertEqual(venta.estado_pago, "pagado")
        self.assertEqual(venta.pagos.count(), 1)
        self.assertEqual(venta.pagos.first().estado, "verificado")
        self.assertEqual(venta.pedido.origen, "para_llevar")
        self.assertEqual(venta.detalles.count(), 1)
        self.assertTrue(venta.movimientos_caja.filter(tipo="venta").exists())

    def test_venta_parcial_y_pago_posterior(self):
        venta, creada = self.crear_venta(monto=Decimal("10.00"))
        self.assertTrue(creada)
        self.assertEqual(venta.estado_pago, "parcial")
        self.assertEqual(venta.saldo_pendiente, Decimal("20.00"))

        services.registrar_pago(venta, self.cajero, self.efectivo, Decimal("20.00"))
        venta.refresh_from_db()
        self.assertEqual(venta.estado_pago, "pagado")
        self.assertEqual(venta.saldo_pendiente, Decimal("0.00"))
        self.assertEqual(venta.movimientos_caja.filter(tipo="venta").count(), 2)

    def test_transferencia_queda_pendiente_hasta_verificacion(self):
        venta, _ = self.crear_venta(metodo=self.transferencia, monto=Decimal("30.00"))
        pago = venta.pagos.first()
        self.assertEqual(pago.estado, "pendiente_verificacion")
        self.assertEqual(venta.estado_pago, "pendiente")
        self.assertFalse(venta.movimientos_caja.filter(tipo="venta").exists())

        services.verificar_pago(pago, self.admin)
        venta.refresh_from_db()
        pago.refresh_from_db()
        self.assertEqual(pago.estado, "verificado")
        self.assertEqual(venta.estado_pago, "pagado")
        self.assertFalse(venta.movimientos_caja.filter(tipo="venta").exists())

    def test_pago_pendiente_reserva_el_saldo(self):
        venta, _ = self.crear_venta(metodo=self.transferencia, monto=Decimal("30.00"))
        self.assertEqual(venta.saldo_disponible, Decimal("0.00"))
        with self.assertRaises(ValidationError):
            services.registrar_pago(venta, self.cajero, self.efectivo, Decimal("1.00"))

    def test_pago_parcial_pendiente_permite_cubrir_el_resto(self):
        venta, _ = self.crear_venta(metodo=self.transferencia, monto=Decimal("10.00"))
        self.assertEqual(venta.saldo_disponible, Decimal("20.00"))
        services.registrar_pago(venta, self.cajero, self.efectivo, Decimal("20.00"))
        venta.refresh_from_db()
        self.assertEqual(venta.saldo_disponible, Decimal("0.00"))
        services.verificar_pago(venta.pagos.get(metodo=self.transferencia), self.admin)
        venta.refresh_from_db()
        self.assertEqual(venta.estado_pago, "pagado")

    def test_producto_inactivo_no_se_puede_vender(self):
        self.producto.activo = False
        self.producto.save(update_fields=["activo"])
        turno = self.abrir_turno()
        with self.assertRaises(ValidationError):
            self.crear_venta(turno=turno)

    def test_descuento_requiere_permiso(self):
        turno = self.abrir_turno()
        with self.assertRaises(PermissionError):
            self.crear_venta(turno=turno, descuento="5.00", descuento_motivo="Promoción")

        turno_admin = self.abrir_turno(usuario=self.admin, caja=self.caja2)
        venta, _ = self.crear_venta(
            usuario=self.admin, turno=turno_admin, descuento="5.00",
            descuento_motivo="Promoción", monto=Decimal("25.00"),
        )
        self.assertEqual(venta.descuento, Decimal("5.00"))
        self.assertEqual(venta.total, Decimal("25.00"))
        self.assertEqual(venta.descuento_autorizado_por, self.admin)

    def test_descuento_autorizado_queda_auditado(self):
        self.abrir_turno(usuario=self.admin, caja=self.caja2)
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("ventas:nueva_venta"), {
            "items": json.dumps([{"producto_id": self.producto.pk, "cantidad": 1}]),
            "token": str(uuid.uuid4()),
            "metodo": self.efectivo.pk,
            "monto": "25.00",
            "descuento": "5.00",
            "descuento_motivo": "Promoción de prueba",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            Auditoria.objects.filter(accion="descuento", entidad="Venta").exists()
        )

    def test_anulacion_en_efectivo_registra_devolucion(self):
        turno = self.abrir_turno(monto="100.00")
        venta, _ = self.crear_venta(turno=turno, monto=Decimal("30.00"))
        services.anular_venta(venta, self.dueno, "Cliente canceló")
        venta.refresh_from_db()
        turno.refresh_from_db()
        self.assertEqual(venta.estado, "anulada")
        self.assertEqual(venta.estado_pago, "reembolsado")
        self.assertEqual(venta.pagos.first().estado, "reembolsado")
        self.assertTrue(venta.movimientos_caja.filter(tipo="devolucion").exists())
        self.assertEqual(turno.efectivo_calculado(), Decimal("100.00"))

    def test_cajero_no_puede_anular_ni_verificar(self):
        venta, _ = self.crear_venta(metodo=self.transferencia, monto=Decimal("30.00"))
        pago = venta.pagos.first()
        self.client.force_login(self.cajero)
        respuesta = self.client.post(reverse("ventas:venta_anular", args=[venta.pk]), {"motivo": "X"})
        self.assertEqual(respuesta.status_code, 403)
        respuesta = self.client.post(reverse("ventas:pago_verificar", args=[pago.pk]))
        self.assertEqual(respuesta.status_code, 403)


class PantallasTests(BaseVentasTestCase):
    def test_pantallas_principales_del_cajero(self):
        turno = self.abrir_turno()
        venta, _ = self.crear_venta(turno=turno)
        self.client.force_login(self.cajero)
        urls = [
            reverse("ventas:inicio"),
            reverse("ventas:nueva_venta"),
            reverse("ventas:historial"),
            reverse("ventas:pedidos"),
            reverse("ventas:caja_movimientos"),
            reverse("ventas:caja_cerrar"),
            reverse("ventas:venta_detalle", args=[venta.pk]),
            reverse("ventas:venta_ticket", args=[venta.pk]),
            reverse("ventas:pedido_detalle", args=[venta.pedido.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_pantallas_del_dueno(self):
        self.client.force_login(self.dueno)
        for url in (
            reverse("nucleo:dashboard"),
            reverse("ventas:cajas"),
            reverse("ventas:metodos_pago"),
            reverse("ventas:metodo_pago_crear"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_dueno_entra_al_panel_de_caja(self):
        self.client.force_login(self.dueno)
        r = self.client.get(reverse("caja:inicio"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "panel-caja")

    def test_dueno_ve_panel_admin_y_caja_con_bases_distintas(self):
        self.client.force_login(self.dueno)
        r = self.client.get(reverse("nucleo:dashboard"))
        self.assertContains(r, "panel-admin")
        r = self.client.get(reverse("caja:inicio"))
        self.assertContains(r, "panel-caja")


class ConsultasTests(BaseVentasTestCase):
    def test_historial_filtra_por_cajero(self):
        turno1 = self.abrir_turno(usuario=self.cajero, caja=self.caja)
        venta1, _ = self.crear_venta(usuario=self.cajero, turno=turno1)
        turno2 = self.abrir_turno(usuario=self.otro_cajero, caja=self.caja2)
        venta2, _ = self.crear_venta(usuario=self.otro_cajero, turno=turno2)

        self.client.force_login(self.cajero)
        respuesta = self.client.get(reverse("ventas:historial"))
        self.assertContains(respuesta, venta1.numero)
        self.assertNotContains(respuesta, venta2.numero)

        self.client.force_login(self.dueno)
        respuesta = self.client.get(reverse("ventas:historial"))
        self.assertContains(respuesta, venta1.numero)
        self.assertContains(respuesta, venta2.numero)

    def test_dashboard_muestra_ventas_reales(self):
        turno = self.abrir_turno()
        self.crear_venta(turno=turno, monto=Decimal("30.00"))
        self.client.force_login(self.dueno)
        respuesta = self.client.get(reverse("nucleo:dashboard"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ventas del periodo")
        self.assertContains(respuesta, "S/ 30.00")

    def test_pedido_cambia_de_estado(self):
        venta, _ = self.crear_venta()
        pedido = venta.pedido
        self.client.force_login(self.cajero)
        respuesta = self.client.post(
            reverse("ventas:pedido_estado", args=[pedido.pk]), {"estado": "en_preparacion"}
        )
        self.assertEqual(respuesta.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "en_preparacion")

    def test_cancelar_pedido_anula_venta(self):
        venta, _ = self.crear_venta()
        pedido = venta.pedido
        self.client.force_login(self.dueno)
        respuesta = self.client.post(
            reverse("ventas:pedido_estado", args=[pedido.pk]),
            {"estado": "cancelado", "motivo": "Cliente no llegó"},
        )
        self.assertEqual(respuesta.status_code, 302)
        venta.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(venta.estado, "anulada")
        self.assertEqual(pedido.estado, "cancelado")

class MesasYCuentasTests(BaseVentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.mesero = crear_usuario("mesero_ventas_f3", "mesero")
        cls.mesa = Mesa.objects.order_by("numero").first()

    def test_mesero_abre_mesa_y_registra_ronda(self):
        self.client.force_login(self.mesero)
        respuesta = self.client.post(reverse("mesero:mesa_abrir", args=[self.mesa.pk]))
        self.assertEqual(respuesta.status_code, 302)
        cuenta = CuentaMesa.objects.get(mesa=self.mesa)
        self.assertEqual(cuenta.mesero, self.mesero)

        respuesta = self.client.post(reverse("mesero:cuenta_agregar", args=[cuenta.pk]), {
            "items": json.dumps([{"producto_id": self.producto.pk, "cantidad": 2}]),
            "observacion": "sin cebolla",
            "prioridad": "alta",
        })
        self.assertEqual(respuesta.status_code, 302)
        pedido = cuenta.pedidos.get()
        self.assertEqual(pedido.ronda, 1)
        self.assertEqual(pedido.total, Decimal("60.00"))
        self.assertEqual(pedido.prioridad, "alta")

    def test_no_duplica_cuenta_abierta_en_misma_mesa(self):
        c1, creada1 = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        self.assertTrue(creada1)
        c2, creada2 = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        self.assertFalse(creada2)
        self.assertEqual(c1.pk, c2.pk)

    def test_segunda_ronda_cuando_la_primera_ya_no_esta_pendiente(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        pedido1, _ = services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        services.cambiar_estado_pedido(pedido1, "en_preparacion")
        pedido2, es_nueva = services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        self.assertTrue(es_nueva)
        self.assertEqual(pedido2.ronda, 2)

class Fase3ComplementoTests(BaseVentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.mesero = crear_usuario("mesero_f3_extra", "mesero")
        cls.mesa = Mesa.objects.order_by("numero").first()

    def test_mesa_admin_permisos(self):
        self.client.force_login(self.mesero)
        self.assertEqual(self.client.get(reverse("ventas:mesas_lista")).status_code, 200)
        respuesta = self.client.post(reverse("ventas:mesa_crear"), {
            "numero": 99, "nombre": "Mesa 99", "capacidad": 4,
        })
        self.assertEqual(respuesta.status_code, 403)

        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse("ventas:mesa_crear"), {
            "numero": 99, "nombre": "Mesa 99", "capacidad": 4,
        })
        self.assertEqual(respuesta.status_code, 302)

    def test_cancelar_ronda_pendiente(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        pedido, _ = services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        services.cancelar_ronda_pedido(pedido, self.mesero, "error", autorizado=False)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "cancelado")

    def test_cancelar_ronda_en_preparacion_requiere_autorizacion(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        pedido, _ = services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        services.cambiar_estado_pedido(pedido, "en_preparacion")
        with self.assertRaises(ValidationError):
            services.cancelar_ronda_pedido(pedido, self.mesero, "error", autorizado=False)
        services.cancelar_ronda_pedido(pedido, self.admin, "error", autorizado=True)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, "cancelado")

    def test_polling_endpoints(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse("mesero:cuenta_json", args=[cuenta.pk]))
        self.assertEqual(respuesta.status_code, 200)
        respuesta = self.client.get(reverse("ventas:caja_cuenta_json", args=[cuenta.pk]))
        self.assertEqual(respuesta.status_code, 200)

    def test_caja_cobra_cuenta(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        services.solicitar_cobro_cuenta(cuenta, self.mesero)
        turno = self.abrir_turno(usuario=self.cajero)
        self.client.force_login(self.cajero)
        respuesta = self.client.get(reverse("ventas:caja_cobrar_cuenta", args=[cuenta.pk]))
        self.assertEqual(respuesta.status_code, 302)
        venta = cuenta.venta
        self.assertIsNotNone(venta)
        self.assertEqual(venta.total, Decimal("30.00"))

    def test_caja_mesas_renderiza_libres_y_ocupadas(self):
        """Regresion: /caja/mesas/ no debe fallar por mesas sin cuenta abierta."""
        services.abrir_cuenta_mesa(self.mesero, self.mesa)
        self.client.force_login(self.cajero)
        respuesta = self.client.get(reverse("caja:mesas"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Ver detalles")
        self.assertContains(respuesta, "Cobrar")

    def test_mesero_no_gestiona_mesas(self):
        self.client.force_login(self.mesero)
        respuesta = self.client.get(reverse("ventas:mesas_lista"))
        self.assertEqual(respuesta.status_code, 200)
        respuesta = self.client.post(reverse("ventas:mesa_crear"), {
            "numero": 7, "nombre": "Mesa 7", "capacidad": 4,
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_polling_requiere_permiso(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        self.client.force_login(self.cajero)  # cajero has ventas.ver, mesas.ver
        respuesta = self.client.get(reverse("mesero:cuenta_json", args=[cuenta.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.client.force_login(self.mesero)
        respuesta = self.client.get(reverse("ventas:caja_cuenta_json", args=[cuenta.pk]))
        # mesero no tiene ventas.ver
        self.assertEqual(respuesta.status_code, 403)

    def test_anular_venta_cuenta_cancela_rondas(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        turno = self.abrir_turno(usuario=self.cajero)
        venta, _ = services.obtener_o_crear_venta_cuenta(self.cajero, turno, cuenta)
        services.anular_venta(venta, self.admin, "error")
        self.assertTrue(cuenta.pedidos.filter(estado="cancelado").exists())
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.estado, "cancelada")


class MeseroFlujoAtencionTests(BaseVentasTestCase):
    """Reglas del panel de mesero: no cobrar sin consumo y no agregar tras solicitar cobro."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.mesero = crear_usuario("mesero_flujo", "mesero")
        cls.mesa = Mesa.objects.order_by("numero").first()

    def _cuenta_con_pedido(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        return cuenta

    def test_no_solicita_cobro_sin_consumos(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        self.client.force_login(self.mesero)
        respuesta = self.client.post(reverse("mesero:cuenta_cobrar", args=[cuenta.pk]))
        self.assertEqual(respuesta.status_code, 302)
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.estado, "abierta")
        with self.assertRaises(ValidationError):
            services.solicitar_cobro_cuenta(cuenta, self.mesero)

    def test_no_agrega_pedido_con_cobro_solicitado(self):
        cuenta = self._cuenta_con_pedido()
        services.solicitar_cobro_cuenta(cuenta, self.mesero)
        self.client.force_login(self.mesero)
        respuesta = self.client.post(reverse("mesero:cuenta_agregar", args=[cuenta.pk]), {
            "items": json.dumps([{"producto_id": self.producto.pk, "cantidad": 1}]),
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(cuenta.pedidos.count(), 1)
        with self.assertRaises(ValidationError):
            services.crear_ronda_pedido(
                self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
            )

    def test_no_cierra_cuenta_con_consumos_sin_pago(self):
        cuenta = self._cuenta_con_pedido()
        with self.assertRaises(ValidationError):
            services.cerrar_cuenta_mesa(cuenta, self.mesero)
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.estado, "abierta")

    def test_detalle_muestra_consumo_y_acciones_correctas(self):
        cuenta = self._cuenta_con_pedido()
        self.client.force_login(self.mesero)
        respuesta = self.client.get(reverse("mesero:cuenta_detalle", args=[cuenta.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Platos consumidos")
        self.assertContains(respuesta, self.producto.nombre)
        self.assertContains(respuesta, "Solicitar cobro")
        self.assertContains(respuesta, "Agregar otra ronda")
        self.assertNotContains(respuesta, "Cobrar en caja")
        self.assertNotContains(respuesta, "Cerrar cuenta")

    def test_detalle_cuenta_vacia_no_muestra_solicitar_cobro(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        self.client.force_login(self.mesero)
        respuesta = self.client.get(reverse("mesero:cuenta_detalle", args=[cuenta.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Solicitar cobro")
        self.assertContains(respuesta, "Liberar mesa")


class MeseroPosRapidoTests(BaseVentasTestCase):
    """POS de mesas del inicio del mesero: catálogo, selector de mesas y pedido rápido."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.mesero = crear_usuario("mesero_pos", "mesero")
        cls.mesa = Mesa.objects.order_by("numero").first()

    def _items(self, cantidad=1):
        return json.dumps([{"producto_id": self.producto.pk, "cantidad": cantidad}])

    def test_inicio_muestra_catalogo_chips_y_selector(self):
        self.client.force_login(self.mesero)
        respuesta = self.client.get(reverse("mesero:inicio"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "chip-filtro")
        self.assertContains(respuesta, "data-filtro-categoria")
        self.assertContains(respuesta, "mesa-opcion")
        self.assertContains(respuesta, "Agregar al pedido")
        self.assertContains(respuesta, self.producto.nombre)

    def test_pedido_rapido_abre_mesa_libre_y_crea_ronda(self):
        self.client.force_login(self.mesero)
        respuesta = self.client.post(reverse("mesero:pedido_rapido"), {
            "mesa": self.mesa.pk,
            "items": self._items(2),
            "prioridad": "alta",
        })
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["ok"])
        self.assertTrue(datos["abierta_ahora"])
        self.assertEqual(datos["rondas"], 1)
        cuenta = CuentaMesa.objects.get(pk=datos["cuenta_id"])
        self.assertEqual(cuenta.estado, "abierta")
        self.assertEqual(cuenta.mesa_id, self.mesa.pk)
        pedido = cuenta.pedidos.get()
        self.assertEqual(pedido.ronda, 1)
        self.assertEqual(pedido.prioridad, "alta")
        self.assertEqual(pedido.detalles.get().cantidad, 2)

    def test_pedido_rapido_actualiza_ronda_pendiente_en_mesa_ocupada(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        self.client.force_login(self.mesero)
        respuesta = self.client.post(reverse("mesero:pedido_rapido"), {
            "mesa": self.mesa.pk,
            "items": self._items(3),
        })
        datos = respuesta.json()
        self.assertTrue(datos["ok"])
        self.assertFalse(datos["abierta_ahora"])
        self.assertEqual(datos["rondas"], 1)
        self.assertEqual(cuenta.pedidos.count(), 1)
        self.assertEqual(cuenta.pedidos.get().detalles.get().cantidad, 3)

    def test_pedido_rapido_bloquea_mesa_con_cobro_solicitado(self):
        cuenta, _ = services.abrir_cuenta_mesa(self.mesero, self.mesa)
        services.crear_ronda_pedido(
            self.mesero, cuenta, [{"producto_id": self.producto.pk, "cantidad": 1}]
        )
        services.solicitar_cobro_cuenta(cuenta, self.mesero)
        self.client.force_login(self.mesero)
        respuesta = self.client.post(reverse("mesero:pedido_rapido"), {
            "mesa": self.mesa.pk,
            "items": self._items(),
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(respuesta.json()["ok"])
        self.assertEqual(cuenta.pedidos.count(), 1)

    def test_pedido_rapido_sin_items_responde_error(self):
        self.client.force_login(self.mesero)
        respuesta = self.client.post(reverse("mesero:pedido_rapido"), {
            "mesa": self.mesa.pk,
            "items": "[]",
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(respuesta.json()["ok"])

    def test_pedido_rapido_mesa_invalida_responde_error(self):
        self.client.force_login(self.mesero)
        respuesta = self.client.post(reverse("mesero:pedido_rapido"), {
            "mesa": 999999,
            "items": self._items(),
        })
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(respuesta.json()["ok"])


class ValidacionDatosVentasTests(BaseVentasTestCase):
    """La captura de datos rechaza nombres con números, documentos no numéricos y cantidades excesivas."""

    def test_venta_rechaza_cliente_con_numeros(self):
        with self.assertRaises(ValidationError):
            self.crear_venta(cliente_nombre="Ana 2")

    def test_venta_rechaza_documento_no_numerico(self):
        with self.assertRaises(ValidationError):
            self.crear_venta(cliente_documento="ABC123")

    def test_venta_rechaza_cantidad_excesiva(self):
        with self.assertRaises(ValidationError):
            self.crear_venta(items=[{"producto_id": self.producto.pk, "cantidad": 1000}])

    def test_venta_rechaza_item_con_formato_invalido(self):
        with self.assertRaises(ValidationError):
            self.crear_venta(items=["no-es-un-dict"])

    def test_mesa_form_exige_numero_mayor_a_cero(self):
        from apps.ventas.forms import MesaForm

        form = MesaForm(data={"numero": 0, "nombre": "Mesa cero", "capacidad": 4, "activa": True})
        self.assertFalse(form.is_valid())
        self.assertIn("numero", form.errors)

    def test_mesa_form_exige_capacidad_mayor_a_cero(self):
        from apps.ventas.forms import MesaForm

        form = MesaForm(data={"numero": 12, "nombre": "", "capacidad": 0, "activa": True})
        self.assertFalse(form.is_valid())
        self.assertIn("capacidad", form.errors)

    def test_mesa_form_rechaza_nombre_con_simbolos_raros(self):
        from apps.ventas.forms import MesaForm

        form = MesaForm(data={"numero": 13, "nombre": "Mesa <x>", "capacidad": 4, "activa": True})
        self.assertFalse(form.is_valid())
        self.assertIn("nombre", form.errors)
