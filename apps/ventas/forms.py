from decimal import Decimal

from django import forms

from apps.nucleo.validaciones import PATRON_COMERCIAL, validar_nombre_comercial

from .models import Caja, Mesa, MetodoPago

# Límite superior coherente con max_digits=10, decimal_places=2.
MONTO_MAXIMO = Decimal("99999999.99")
# Cantidades y números de mesa razonables para el giro del negocio.
NUMERO_MAXIMO = 9999
CAPACIDAD_MAXIMA = 99
ORDEN_MAXIMO = 999


def _monto_input(attrs=None):
    base = {"step": "0.01", "inputmode": "decimal"}
    base.update(attrs or {})
    return forms.NumberInput(attrs=base)


class AperturaCajaForm(forms.Form):
    caja = forms.ModelChoiceField(
        label="Caja", queryset=Caja.objects.filter(activa=True), empty_label=None,
        widget=forms.Select(attrs={"class": "campo-select"}),
    )
    monto_inicial = forms.DecimalField(
        label="Monto inicial (S/)", max_digits=10, decimal_places=2,
        min_value=Decimal("0.00"), max_value=MONTO_MAXIMO,
        widget=_monto_input({"min": "0"}),
    )
    observacion = forms.CharField(
        label="Observación (opcional)", max_length=200, required=False,
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 200}),
    )


class CierreCajaForm(forms.Form):
    monto_contado = forms.DecimalField(
        label="Efectivo contado (S/)", max_digits=10, decimal_places=2,
        min_value=Decimal("0.00"), max_value=MONTO_MAXIMO,
        widget=_monto_input({"min": "0"}),
    )
    observacion = forms.CharField(
        label="Observación (opcional)", max_length=300, required=False,
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 300}),
    )


class MovimientoCajaForm(forms.Form):
    tipo = forms.ChoiceField(label="Tipo", choices=[("ingreso", "Ingreso"), ("egreso", "Egreso")])
    monto = forms.DecimalField(
        label="Monto (S/)", max_digits=10, decimal_places=2,
        min_value=Decimal("0.01"), max_value=MONTO_MAXIMO,
        widget=_monto_input({"min": "0.01"}),
    )
    descripcion = forms.CharField(
        label="Motivo", max_length=200,
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 200}),
    )


class PagoForm(forms.Form):
    metodo = forms.ModelChoiceField(
        label="Método de pago", queryset=MetodoPago.objects.filter(activo=True), empty_label=None,
    )
    monto = forms.DecimalField(
        label="Monto (S/)", max_digits=10, decimal_places=2,
        min_value=Decimal("0.01"), max_value=MONTO_MAXIMO,
        widget=_monto_input({"min": "0.01"}),
    )
    referencia = forms.CharField(
        label="Referencia (opcional)", max_length=100, required=False,
        help_text="Número de operación, voucher o dato de la transferencia.",
        widget=forms.TextInput(attrs={"maxlength": 100}),
    )
    observacion = forms.CharField(
        label="Observación (opcional)", max_length=200, required=False,
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 200}),
    )


class AnulacionForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de la anulación", max_length=300, min_length=5,
        widget=forms.Textarea(attrs={"rows": 3, "maxlength": 300}),
    )


class MesaForm(forms.ModelForm):
    numero = forms.IntegerField(
        label="Número", min_value=1, max_value=NUMERO_MAXIMO,
        widget=forms.NumberInput(attrs={"min": "1", "step": "1", "inputmode": "numeric"}),
    )
    capacidad = forms.IntegerField(
        label="Capacidad", min_value=1, max_value=CAPACIDAD_MAXIMA,
        widget=forms.NumberInput(attrs={"min": "1", "step": "1", "inputmode": "numeric"}),
    )

    class Meta:
        model = Mesa
        fields = ["numero", "nombre", "capacidad", "activa"]
        widgets = {
            "nombre": forms.TextInput(attrs={"maxlength": 40, "autocapitalize": "sentences"}),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get("nombre") or "").strip()
        if nombre:
            nombre = validar_nombre_comercial(nombre, "El nombre de la mesa")
        return nombre


class MetodoPagoForm(forms.ModelForm):
    orden = forms.IntegerField(
        label="Orden", min_value=0, max_value=ORDEN_MAXIMO, required=False, initial=0,
        widget=forms.NumberInput(attrs={"min": "0", "step": "1", "inputmode": "numeric"}),
    )

    class Meta:
        model = MetodoPago
        fields = ["codigo", "nombre", "afecta_efectivo", "requiere_verificacion", "activo", "orden"]
        widgets = {
            "codigo": forms.TextInput(attrs={"maxlength": 30, "autocapitalize": "none", "autocorrect": "off"}),
            "nombre": forms.TextInput(attrs={"pattern": PATRON_COMERCIAL, "maxlength": 60}),
        }

    def clean_codigo(self):
        # El código es un identificador: sin espacios ni signos.
        return (self.cleaned_data.get("codigo") or "").strip()

    def clean_nombre(self):
        return validar_nombre_comercial(self.cleaned_data.get("nombre"), "El nombre del método")

    def clean_orden(self):
        return self.cleaned_data.get("orden") or 0
