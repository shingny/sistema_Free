from django import forms
from django.db.models import Q

from apps.nucleo.validaciones import PATRON_COMERCIAL, validar_nombre_comercial

from .models import Categoria, Producto


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre", "descripcion", "orden"]
        widgets = {
            "nombre": forms.TextInput(attrs={"pattern": PATRON_COMERCIAL, "maxlength": 60, "autocapitalize": "sentences"}),
            "descripcion": forms.TextInput(attrs={"maxlength": 200}),
            "orden": forms.NumberInput(attrs={"min": "0", "step": "1", "inputmode": "numeric"}),
        }

    def clean_nombre(self):
        nombre = validar_nombre_comercial(self.cleaned_data["nombre"], "El nombre de la categoría")
        if Categoria.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una categoría con ese nombre.")
        return nombre


class ProductoForm(forms.ModelForm):
    quitar_imagen = forms.BooleanField(label="Quitar la imagen actual", required=False)

    class Meta:
        model = Producto
        fields = ["nombre", "descripcion", "categoria", "precio", "imagen"]
        widgets = {
            "nombre": forms.TextInput(attrs={"pattern": PATRON_COMERCIAL, "maxlength": 100}),
            "descripcion": forms.Textarea(attrs={"rows": 3, "maxlength": 500}),
            "imagen": forms.FileInput(attrs={"accept": "image/*"}),
            "precio": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        actual = self.instance.categoria_id
        self.fields["categoria"].queryset = Categoria.objects.filter(Q(activo=True) | Q(pk=actual))
        self.fields["categoria"].empty_label = "Selecciona una categoría"

    def clean_nombre(self):
        return validar_nombre_comercial(self.cleaned_data["nombre"], "El nombre del producto")

    def clean_imagen(self):
        imagen = self.cleaned_data.get("imagen")
        if imagen and hasattr(imagen, "size") and imagen.size > 2 * 1024 * 1024:
            raise forms.ValidationError("La imagen no puede superar los 2 MB.")
        return imagen

    def clean(self):
        datos = super().clean()
        nombre, categoria = datos.get("nombre"), datos.get("categoria")
        if nombre and categoria:
            repetido = Producto.objects.filter(nombre__iexact=nombre, categoria=categoria).exclude(pk=self.instance.pk)
            if repetido.exists():
                self.add_error("nombre", "Ya existe un producto con ese nombre en esta categoría.")
        return datos
