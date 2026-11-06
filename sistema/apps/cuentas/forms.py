from django import forms
from django.contrib.auth.forms import PasswordChangeForm

from apps.nucleo.validaciones import (
    PATRON_DOCUMENTO,
    PATRON_NOMBRE,
    PATRON_TELEFONO,
    PATRON_USUARIO,
    RE_DOCUMENTO,
    RE_TELEFONO,
    RE_USUARIO,
    validar_nombre,
)

from . import servicios
from .models import Usuario


class LoginForm(forms.Form):
    username = forms.CharField(
        label="Usuario", max_length=150,
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username", "autocapitalize": "none"}),
    )
    password = forms.CharField(
        label="Contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )


class _ContactoMixin:
    def clean_first_name(self):
        return validar_nombre(self.cleaned_data.get("first_name"), "Los nombres")

    def clean_last_name(self):
        return validar_nombre(self.cleaned_data.get("last_name"), "Los apellidos")

    def clean_telefono(self):
        telefono = self.cleaned_data.get("telefono", "").strip()
        if telefono and not RE_TELEFONO.match(telefono):
            raise forms.ValidationError("Ingresa un teléfono válido (solo números, +, espacios o guiones).")
        return telefono

    def clean_email(self):
        return self.cleaned_data.get("email", "").strip().lower()


class UsuarioForm(_ContactoMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "documento", "username", "email", "telefono", "rol"]
        labels = {
            "first_name": "Nombres", "last_name": "Apellidos", "documento": "Documento de identidad",
            "username": "Nombre de usuario", "email": "Correo electrónico (opcional)",
            "telefono": "Teléfono (opcional)", "rol": "Rol",
        }

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["documento"].required = False
        self.fields["rol"].required = True
        self.fields["rol"].empty_label = "Selecciona un rol"
        self.fields["rol"].queryset = servicios.roles_asignables(actor)
        if self.instance.pk:
            self.fields["username"].disabled = True  # el usuario no cambia una vez creado
        self.fields["first_name"].widget.attrs.update({"pattern": PATRON_NOMBRE, "autocapitalize": "words", "maxlength": 150})
        self.fields["last_name"].widget.attrs.update({"pattern": PATRON_NOMBRE, "autocapitalize": "words", "maxlength": 150})
        self.fields["documento"].widget.attrs.update({"pattern": PATRON_DOCUMENTO, "maxlength": 12, "inputmode": "text"})
        self.fields["username"].widget.attrs.update({"pattern": PATRON_USUARIO, "maxlength": 30, "autocapitalize": "none"})
        self.fields["telefono"].widget.attrs.update({"pattern": PATRON_TELEFONO, "inputmode": "tel", "maxlength": 20})

    def clean_username(self):
        usuario = self.cleaned_data["username"].strip().lower()
        if not RE_USUARIO.match(usuario):
            raise forms.ValidationError(
                "Usa de 4 a 30 caracteres: letras minúsculas, números, punto, guion o guion bajo."
            )
        existe = Usuario.objects.filter(username__iexact=usuario).exclude(pk=self.instance.pk).exists()
        if existe:
            raise forms.ValidationError("Ese nombre de usuario ya está en uso.")
        return usuario

    def clean_documento(self):
        documento = (self.cleaned_data.get("documento") or "").strip()
        if not documento:
            return None
        if not RE_DOCUMENTO.match(documento):
            raise forms.ValidationError("El documento debe tener entre 8 y 12 caracteres alfanuméricos.")
        return documento


class PerfilForm(_ContactoMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email", "telefono"]
        labels = {"first_name": "Nombres", "last_name": "Apellidos",
                  "email": "Correo electrónico", "telefono": "Teléfono"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["first_name"].widget.attrs.update({"pattern": PATRON_NOMBRE, "autocapitalize": "words", "maxlength": 150})
        self.fields["last_name"].widget.attrs.update({"pattern": PATRON_NOMBRE, "autocapitalize": "words", "maxlength": 150})
        self.fields["telefono"].widget.attrs.update({"pattern": PATRON_TELEFONO, "inputmode": "tel", "maxlength": 20})


class CambiarPasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Contraseña actual"
        self.fields["new_password1"].label = "Contraseña nueva"
        self.fields["new_password2"].label = "Repite la contraseña nueva"
        self.fields["old_password"].widget.attrs.pop("autofocus", None)

    def clean_new_password1(self):
        nueva = self.cleaned_data.get("new_password1")
        if nueva and self.user.check_password(nueva):
            raise forms.ValidationError("La contraseña nueva debe ser distinta de la actual.")
        return nueva
