from django import forms

from apps.nucleo.validaciones import (
    PATRON_COMERCIAL,
    PATRON_RUC,
    PATRON_TELEFONO,
    validar_nombre_comercial,
    validar_telefono,
)

from .models import Configuracion


class ConfiguracionForm(forms.ModelForm):
    quitar_logo = forms.BooleanField(label="Quitar el logo actual", required=False)

    class Meta:
        model = Configuracion
        fields = [
            "nombre_comercial", "razon_social", "ruc", "direccion", "telefono", "correo",
            "horario_atencion", "logo", "moneda", "zona_horaria", "permitir_pago_parcial",
        ]
        widgets = {
            "logo": forms.FileInput(attrs={"accept": "image/*"}),
            "nombre_comercial": forms.TextInput(attrs={"pattern": PATRON_COMERCIAL, "maxlength": 120}),
            "razon_social": forms.TextInput(attrs={"maxlength": 150}),
            "ruc": forms.TextInput(attrs={"pattern": PATRON_RUC, "maxlength": 11, "inputmode": "numeric"}),
            "direccion": forms.TextInput(attrs={"maxlength": 200}),
            "telefono": forms.TextInput(attrs={"pattern": PATRON_TELEFONO, "maxlength": 20, "inputmode": "tel"}),
            "horario_atencion": forms.TextInput(attrs={"maxlength": 150}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # La moneda y la zona horaria son parte de las reglas del proyecto: se muestran, no se editan.
        self.fields["moneda"].disabled = True
        self.fields["zona_horaria"].disabled = True
        self.fields["nombre_comercial"].required = True

    def clean_nombre_comercial(self):
        return validar_nombre_comercial(self.cleaned_data.get("nombre_comercial"), "El nombre comercial")

    def clean_razon_social(self):
        valor = (self.cleaned_data.get("razon_social") or "").strip()
        return validar_nombre_comercial(valor, "La razón social") if valor else ""

    def clean_direccion(self):
        return (self.cleaned_data.get("direccion") or "").strip()

    def clean_horario_atencion(self):
        return (self.cleaned_data.get("horario_atencion") or "").strip()

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "size") and logo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("El logo no puede superar los 2 MB.")
        return logo

    def clean_telefono(self):
        return validar_telefono(self.cleaned_data.get("telefono"))
