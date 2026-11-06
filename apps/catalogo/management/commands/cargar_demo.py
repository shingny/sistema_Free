from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalogo.models import Categoria, Producto

CATEGORIAS = [
    ("Pollos a la brasa", "Pollo a la brasa con papas fritas y ensalada."),
    ("Combos", "Combinaciones para una o varias personas."),
    ("Parrillas", "Carnes a la parrilla."),
    ("Entradas", "Acompañamientos y entradas."),
    ("Bebidas", "Bebidas frías y refrescos."),
    ("Postres", "Postres de la casa."),
]

# (categoría, nombre, descripción, precio en soles)
PRODUCTOS = [
    ("Pollos a la brasa", "Pollo entero", "Pollo entero a la brasa con papas fritas y ensalada.", "65.00"),
    ("Pollos a la brasa", "Medio pollo", "Medio pollo a la brasa con papas fritas y ensalada.", "35.00"),
    ("Pollos a la brasa", "Cuarto de pollo", "Cuarto de pollo a la brasa con papas fritas y ensalada.", "19.00"),
    ("Combos", "Combo familiar", "Pollo entero, papas grandes, ensalada y chicha de 1 litro.", "79.00"),
    ("Combos", "Combo personal", "Cuarto de pollo, papas personales y gaseosa.", "22.00"),
    ("Parrillas", "Parrilla personal", "Carne, pollo y chorizo a la parrilla con papas.", "32.00"),
    ("Parrillas", "Parrilla familiar", "Parrilla para compartir con papas y ensalada.", "75.00"),
    ("Entradas", "Papas fritas", "Porción de papas fritas crocantes.", "8.00"),
    ("Entradas", "Ensalada fresca", "Lechuga, tomate, zanahoria y limón.", "6.00"),
    ("Bebidas", "Chicha morada (jarra)", "Jarra de chicha morada de la casa.", "12.00"),
    ("Bebidas", "Chicha morada (vaso)", "Vaso de chicha morada de la casa.", "4.00"),
    ("Bebidas", "Inca Kola 500 ml", "Gaseosa Inca Kola personal.", "5.00"),
    ("Bebidas", "Coca-Cola 500 ml", "Gaseosa Coca-Cola personal.", "5.00"),
    ("Bebidas", "Agua mineral", "Botella de agua mineral sin gas.", "3.00"),
    ("Postres", "Flan casero", "Flan de la casa con caramelo.", "7.00"),
    ("Postres", "Mazamorra morada", "Mazamorra morada tradicional.", "6.00"),
]


class Command(BaseCommand):
    help = "Carga categorías y productos de ejemplo para probar el sistema (idempotente)."

    def handle(self, *args, **options):
        categorias_nuevas = 0
        for orden, (nombre, descripcion) in enumerate(CATEGORIAS, start=1):
            _, creada = Categoria.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": descripcion, "orden": orden, "activo": True},
            )
            categorias_nuevas += int(creada)

        productos_nuevos = 0
        for categoria_nombre, nombre, descripcion, precio in PRODUCTOS:
            categoria = Categoria.objects.get(nombre=categoria_nombre)
            _, creado = Producto.objects.get_or_create(
                categoria=categoria,
                nombre=nombre,
                defaults={
                    "descripcion": descripcion,
                    "precio": Decimal(precio),
                    "activo": True,
                },
            )
            productos_nuevos += int(creado)

        self.stdout.write(self.style.SUCCESS(
            f"Categorías nuevas: {categorias_nuevas}. Productos nuevos: {productos_nuevos}."
        ))
