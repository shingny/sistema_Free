import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.catalogo.models import Categoria, Producto
from apps.cuentas.testing import crear_usuario, preparar_roles
from apps.nucleo.models import Auditoria


class BaseCatalogo(TestCase):
    def setUp(self):
        preparar_roles()
        self.dueno = crear_usuario("duenio", "dueno")
        self.cajero = crear_usuario("cajero1", "cajero")
        self.cat = Categoria.objects.create(nombre="Pollos", orden=1)

    def datos(self, **cambios):
        d = {"nombre": "Pollo entero", "descripcion": "Con papas", "categoria": self.cat.pk, "precio": "58.90"}
        d.update(cambios)
        return d


class ProductosTests(BaseCatalogo):
    def test_crear_producto_guarda_precio_exacto(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse("catalogo:producto_crear"), self.datos())
        p = Producto.objects.get(nombre="Pollo entero")
        self.assertEqual(p.precio, Decimal("58.90"))
        self.assertTrue(p.activo)
        self.assertTrue(Auditoria.objects.filter(accion="crear", modulo="productos").exists())

    def test_precio_debe_ser_mayor_a_cero(self):
        self.client.force_login(self.dueno)
        r = self.client.post(reverse("catalogo:producto_crear"), self.datos(precio="0"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Producto.objects.count(), 0)

    def test_nombre_repetido_en_la_misma_categoria(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse("catalogo:producto_crear"), self.datos())
        r = self.client.post(reverse("catalogo:producto_crear"), self.datos(nombre="pollo ENTERO"))
        self.assertContains(r, "Ya existe un producto")

    def test_cambio_de_precio_queda_auditado(self):
        p = Producto.objects.create(nombre="Medio pollo", categoria=self.cat, precio=Decimal("32.00"))
        self.client.force_login(self.dueno)
        self.client.post(reverse("catalogo:producto_editar", args=[p.pk]), self.datos(nombre="Medio pollo", precio="35.50"))
        p.refresh_from_db()
        self.assertEqual(p.precio, Decimal("35.50"))
        reg = Auditoria.objects.get(accion="cambio_precio")
        self.assertEqual(reg.antes["precio"], "32.00")
        self.assertEqual(reg.despues["precio"], "35.50")

    def test_productos_inactivos_no_estan_disponibles(self):
        activo = Producto.objects.create(nombre="Papas", categoria=self.cat, precio=Decimal("8"))
        inactivo = Producto.objects.create(nombre="Ensalada", categoria=self.cat, precio=Decimal("9"), activo=False)
        self.assertIn(activo, Producto.objects.disponibles())
        self.assertNotIn(inactivo, Producto.objects.disponibles())

    def test_producto_de_categoria_inactiva_no_esta_disponible(self):
        p = Producto.objects.create(nombre="Papas", categoria=self.cat, precio=Decimal("8"))
        self.cat.activo = False
        self.cat.save()
        self.assertNotIn(p, Producto.objects.disponibles())

    def test_desactivar_producto_via_post(self):
        p = Producto.objects.create(nombre="Papas", categoria=self.cat, precio=Decimal("8"))
        self.client.force_login(self.dueno)
        self.client.post(reverse("catalogo:producto_estado", args=[p.pk]))
        p.refresh_from_db()
        self.assertFalse(p.activo)

    def test_no_se_activa_producto_de_categoria_inactiva(self):
        p = Producto.objects.create(nombre="Papas", categoria=self.cat, precio=Decimal("8"), activo=False)
        self.cat.activo = False
        self.cat.save()
        self.client.force_login(self.dueno)
        self.client.post(reverse("catalogo:producto_estado", args=[p.pk]))
        p.refresh_from_db()
        self.assertFalse(p.activo)

    def test_cajero_no_puede_cambiar_precios_ni_crear(self):
        p = Producto.objects.create(nombre="Papas", categoria=self.cat, precio=Decimal("8"))
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.post(reverse("catalogo:producto_crear"), self.datos()).status_code, 403)
        self.assertEqual(self.client.post(reverse("catalogo:producto_editar", args=[p.pk]), self.datos(precio="1")).status_code, 403)
        p.refresh_from_db()
        self.assertEqual(p.precio, Decimal("8.00"))

    def test_filtros_de_listado(self):
        Producto.objects.create(nombre="Papas", categoria=self.cat, precio=Decimal("8"))
        Producto.objects.create(nombre="Ensalada", categoria=self.cat, precio=Decimal("9"), activo=False)
        self.client.force_login(self.dueno)
        r = self.client.get(reverse("catalogo:productos"), {"estado": "inactivo"})
        self.assertContains(r, "Ensalada")
        self.assertNotContains(r, "Papas")

    def test_imagen_demasiado_grande_se_rechaza(self):
        self.client.force_login(self.dueno)
        grande = SimpleUploadedFile("foto.jpg", b"0" * (2 * 1024 * 1024 + 1), content_type="image/jpeg")
        r = self.client.post(reverse("catalogo:producto_crear"), {**self.datos(), "imagen": grande})
        self.assertEqual(Producto.objects.count(), 0)
        self.assertEqual(r.status_code, 200)

    def test_exportar_requiere_permiso_reportes(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("catalogo:productos_exportar")).status_code, 403)
        self.client.force_login(self.dueno)
        r = self.client.get(reverse("catalogo:productos_exportar"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])


class CategoriasTests(BaseCatalogo):
    def test_crear_y_nombre_unico(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse("catalogo:categoria_crear"), {"nombre": "Combos", "descripcion": "", "orden": 2})
        self.assertTrue(Categoria.objects.filter(nombre="Combos").exists())
        r = self.client.post(reverse("catalogo:categoria_crear"), {"nombre": "combos", "descripcion": "", "orden": 3})
        self.assertContains(r, "Ya existe una categoría")

    def test_no_desactiva_categoria_con_productos_activos(self):
        Producto.objects.create(nombre="Papas", categoria=self.cat, precio=Decimal("8"))
        self.client.force_login(self.dueno)
        self.client.post(reverse("catalogo:categoria_estado", args=[self.cat.pk]))
        self.cat.refresh_from_db()
        self.assertTrue(self.cat.activo)

    def test_desactiva_categoria_sin_productos_activos(self):
        self.client.force_login(self.dueno)
        self.client.post(reverse("catalogo:categoria_estado", args=[self.cat.pk]))
        self.cat.refresh_from_db()
        self.assertFalse(self.cat.activo)

    def test_cargar_imagenes_asigna_imagen(self):
        cat = self.cat
        producto = Producto.objects.create(nombre="Pollo entero", categoria=cat, precio=Decimal("30.00"))
        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as tmp:
            origen = Path(tmp) / "origen"
            media = Path(tmp) / "media"
            origen.mkdir()
            media.mkdir()
            Image.new("RGB", (2, 2), "white").save(origen / "pollo entero.png")
            with override_settings(MEDIA_ROOT=media):
                call_command("cargar_imagenes_productos", origen=str(origen), verbosity=0)
                producto.refresh_from_db()
                self.assertTrue(bool(producto.imagen))

class ImagenesProductosTests(TestCase):
    def setUp(self):
        preparar_roles()
        self.dueno = crear_usuario("dueno_img", "dueno")
        self.cat = Categoria.objects.create(nombre="Pollos", orden=1)

    def test_cargar_imagenes_asigna_imagen(self):
        producto = Producto.objects.create(nombre="Pollo entero", categoria=self.cat, precio=Decimal("30.00"))
        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as tmp:
            origen = Path(tmp) / "origen"
            media = Path(tmp) / "media"
            origen.mkdir()
            media.mkdir()
            Image.new("RGB", (2, 2), "white").save(origen / "pollo entero.png")
            with override_settings(MEDIA_ROOT=media):
                call_command("cargar_imagenes_productos", origen=str(origen), verbosity=0)
                producto.refresh_from_db()
                self.assertTrue(bool(producto.imagen))
