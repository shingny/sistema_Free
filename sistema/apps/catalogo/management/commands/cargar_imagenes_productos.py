import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from apps.catalogo.models import Producto


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in texto.lower()).split())


MANUAL = {
    "chicha morada": ["chicha morada (jarra)", "chicha morada (vaso)"],
    "personal inka kola": ["inca kola 500 ml"],
    "pollo combo familiar": ["combo familiar"],
    "pollo entero": ["pollo entero"],
    "porcion de ensalada": ["ensalada fresca"],
    "porcion de papa": ["papas fritas"],
}


def _origen_por_defecto():
    """Carpeta de fotos dentro del repo; si no existe, usa la carpeta histórica."""
    dentro = Path(settings.BASE_DIR) / "imagenes"
    historica = Path(settings.BASE_DIR).parent / "imagenes"
    return str(dentro if dentro.exists() else historica)


class Command(BaseCommand):
    help = "Asigna imágenes de la carpeta imagenes a los productos por nombre."

    def add_arguments(self, parser):
        parser.add_argument(
            "--origen",
            default=_origen_por_defecto(),
            help="Carpeta con las imágenes.",
        )
        parser.add_argument("--force", action="store_true", help="Reemplaza imágenes ya asignadas.")

    def handle(self, *args, **options):
        origen = Path(options["origen"])
        if not origen.exists():
            self.stderr.write(f"No existe la carpeta: {origen}")
            return

        extensiones = {".png", ".jpg", ".jpeg", ".webp"}
        asignadas = 0
        sin_producto = []
        productos = list(Producto.objects.all())

        for imagen in sorted(origen.rglob("*")):
            if not imagen.is_file() or imagen.suffix.lower() not in extensiones:
                continue
            clave = normalizar(imagen.stem)
            nombres_objetivo = MANUAL.get(clave, [])
            if not nombres_objetivo:
                for producto in productos:
                    pn = normalizar(producto.nombre)
                    if clave and (clave in pn or pn in clave):
                        nombres_objetivo.append(producto.nombre)

            objetivos = Producto.objects.none()
            for nombre in nombres_objetivo:
                objetivos = objetivos | Producto.objects.filter(nombre__iexact=nombre)
            if not objetivos.exists():
                sin_producto.append(str(imagen))
                continue

            for producto in objetivos:
                if producto.imagen and not options["force"]:
                    self.stdout.write(f"Ya tiene imagen: {producto.nombre}")
                    continue
                with imagen.open("rb") as archivo:
                    producto.imagen.save(imagen.name, File(archivo), save=True)
                asignadas += 1
                self.stdout.write(self.style.SUCCESS(f"Imagen asignada: {producto.nombre} <- {imagen.name}"))

        if sin_producto:
            self.stdout.write(self.style.WARNING("Imágenes sin producto coincidente:"))
            for ruta in sin_producto:
                self.stdout.write(f"  - {ruta}")

        self.stdout.write(f"Total asignadas: {asignadas}")