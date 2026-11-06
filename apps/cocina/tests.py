import json
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.catalogo.models import Categoria, Producto
from apps.cuentas.testing import CLAVE, crear_usuario, preparar_roles
from apps.ventas import services
from apps.ventas.models import Caja, Mesa, MetodoPago, Pedido, Venta


class CocinaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        preparar_roles()
        cls.dueno = crear_usuario("dueno_cocina", "dueno")
        cls.cajero = crear_usuario("cajero_cocina", "cajero")
        cls.cocinero = crear_usuario("cocinero_cocina", "cocinero")
        cls.categoria = Categoria.objects.create(nombre="Cocina de prueba", orden=1)
        cls.producto = Producto.objects.create(
            nombre="Pollo a la brasa de prueba", categoria=cls.categoria, precio=Decimal("30.00")
        )
        cls.caja, _ = Caja.objects.get_or_create(
            codigo="CAJA-01", defaults={"nombre": "Caja principal"}
        )
        cls.efectivo, _ = MetodoPago.objects.get_or_create(
            codigo="efectivo", defaults={"nombre": "Efectivo", "afecta_efectivo": True, "orden": 1}
        )
        cls.mesa = Mesa.objects.create(numero=99, capacidad=4)

    def setUp(self):
        self.turno = services.abrir_caja(self.cajero, self.caja, Decimal("100.00"))
        self.venta, _ = services.crear_venta(
            self.cajero,
            self.turno,
            [{"producto_id": self.producto.pk, "cantidad": 1}],
            token=uuid.uuid4(),
            origen="salon",
            mesa=self.mesa,
        )
        self.pedido = self.venta.pedido

    def test_pedido_salon_sin_pago_queda_pendiente(self):
        self.assertEqual(self.pedido.origen, "salon")
        self.assertEqual(self.pedido.mesa, self.mesa)
        self.assertEqual(self.venta.estado_pago, "pendiente")
        self.assertEqual(self.venta.total_pagado, Decimal("0.00"))

    def test_salon_requiere_mesa_activa(self):
        with self.assertRaises(ValidationError):
            services.crear_venta(
                self.cajero,
                self.turno,
                [{"producto_id": self.producto.pk, "cantidad": 1}],
                token=uuid.uuid4(),
                origen="salon",
            )

    def test_cocina_ve_y_avanza_pedido(self):
        self.client.force_login(self.cocinero)
        respuesta = self.client.get(reverse("cocina:tablero"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.pedido.numero)
        self.assertContains(respuesta, "panel-cocina")

        respuesta = self.client.post(reverse("cocina:avanzar", args=[self.pedido.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "en_preparacion")

        respuesta = self.client.post(reverse("cocina:avanzar", args=[self.pedido.pk]))
        self.assertEqual(respuesta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "listo")

    def test_cajero_no_puede_entrar_a_cocina(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("cocina:tablero")).status_code, 403)

    def test_cocinero_no_puede_entrar_a_caja(self):
        self.client.force_login(self.cocinero)
        self.assertEqual(self.client.get(reverse("caja:inicio")).status_code, 403)

    def test_login_de_cocinero_redirige_a_cocina(self):
        respuesta = self.client.post(
            reverse("cuentas:login"),
            {"username": self.cocinero.username, "password": CLAVE},
        )
        self.assertRedirects(respuesta, reverse("cocina:tablero"))

    def test_dueno_ve_panel_de_cocina(self):
        self.client.force_login(self.dueno)
        respuesta = self.client.get(reverse("cocina:tablero"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "panel-cocina")

    def test_pos_permite_crear_pedido_de_salon_sin_cobrar(self):
        self.client.force_login(self.cajero)
        respuesta = self.client.get(reverse("caja:nueva_venta"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'name="origen"')
        self.assertContains(respuesta, 'name="mesa"')

        respuesta = self.client.post(reverse("caja:nueva_venta"), {
            "items": json.dumps([{"producto_id": self.producto.pk, "cantidad": 2}]),
            "token": str(uuid.uuid4()),
            "origen": "salon",
            "mesa": self.mesa.pk,
            "cliente_nombre": "Cliente de mesa",
            "descuento": "0",
        })
        self.assertEqual(respuesta.status_code, 302)
        pedido = Pedido.objects.exclude(pk=self.pedido.pk).get(mesa=self.mesa)
        self.assertEqual(pedido.origen, "salon")
        self.assertEqual(pedido.total, Decimal("60.00"))
        venta = Venta.objects.get(pedido=pedido)
        self.assertEqual(venta.estado_pago, "pendiente")

    def test_tablero_json(self):
        self.client.force_login(self.cocinero)
        respuesta = self.client.get(reverse("cocina:tablero_json"))
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertIn("pedidos", datos)
        self.assertTrue(any(p["numero"] == self.pedido.numero for p in datos["pedidos"]))

    def test_historial_y_agotados(self):
        self.client.force_login(self.cocinero)
        self.assertEqual(self.client.get(reverse("cocina:historial")).status_code, 200)
        self.assertEqual(self.client.get(reverse("cocina:agotados")).status_code, 200)

    def test_reportar_agotado(self):
        self.client.force_login(self.cocinero)
        respuesta = self.client.post(reverse("cocina:reportar_agotado"), {
            "producto": self.producto.pk, "descripcion": "sin stock",
        })
        self.assertEqual(respuesta.status_code, 302)
        from apps.ventas.models import IncidenciaCocina
        self.assertTrue(IncidenciaCocina.objects.filter(producto=self.producto).exists())

    def test_tablero_json_requiere_permiso(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("cocina:tablero_json")).status_code, 403)
