from django.db import migrations


def crear_mesas(apps, schema_editor):
    Mesa = apps.get_model("ventas", "Mesa")
    for numero in range(1, 7):
        Mesa.objects.get_or_create(numero=numero, defaults={"capacidad": 4, "activa": True})


def eliminar_mesas(apps, schema_editor):
    Mesa = apps.get_model("ventas", "Mesa")
    Mesa.objects.filter(numero__in=range(1, 7)).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ventas", "0003_mesa_pedido_mesa"),
    ]

    operations = [
        migrations.RunPython(crear_mesas, eliminar_mesas),
    ]
