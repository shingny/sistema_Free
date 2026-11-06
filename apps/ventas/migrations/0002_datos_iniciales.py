from django.db import migrations


def sembrar(apps, schema_editor):
    Caja = apps.get_model("ventas", "Caja")
    MetodoPago = apps.get_model("ventas", "MetodoPago")

    Caja.objects.get_or_create(
        codigo="CAJA-01",
        defaults={"nombre": "Caja principal", "activa": True},
    )

    metodos = [
        ("efectivo", "Efectivo", True, False, 1),
        ("tarjeta", "Tarjeta", False, False, 2),
        ("transferencia", "Transferencia", False, True, 3),
        ("yape_plin", "Yape / Plin", False, True, 4),
    ]
    for codigo, nombre, afecta_efectivo, requiere_verificacion, orden in metodos:
        MetodoPago.objects.get_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "afecta_efectivo": afecta_efectivo,
                "requiere_verificacion": requiere_verificacion,
                "activo": True,
                "orden": orden,
            },
        )


def revertir(apps, schema_editor):
    """No se eliminan datos operativos al revertir la migración."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("ventas", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(sembrar, revertir),
    ]
