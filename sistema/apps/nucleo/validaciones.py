"""Validaciones de entrada reutilizables.

Centraliza las reglas de captura de datos del sistema para que la validación
del servidor y los atributos HTML (`pattern`, `inputmode`, etc.) sean coherentes.

Convención:
- Las constantes `RE_*` son para validar en Python (``re.match``).
- Las constantes `PATRON_*` son para el atributo ``pattern`` del HTML (sin ^$,
  porque el navegador ya ancla el patrón a todo el valor).
"""
import re

from django.core.exceptions import ValidationError

# ---------------------------------------------------------------- nombres propios
# Solo letras (con acentos y ñ) y separadores habituales: espacio, apóstrofo,
# punto y guion (para "María José", "O'Brien", "Jean-Pierre").
_LETRA = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
RE_NOMBRE = re.compile(rf"^[{_LETRA}][{_LETRA}' .-]*$")
PATRON_NOMBRE = rf"[{_LETRA}][{_LETRA}' .-]{{1,}}"

# Nombres comerciales (productos, categorías, negocio): además de letras, admiten
# números y signos suaves (&, (), ., coma, /, -, +).
_LETRA_COM = "A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ"
RE_NOMBRE_COMERCIAL = re.compile(rf"^[{_LETRA_COM}][{_LETRA_COM} &'().,o/+°-]*$")
PATRON_COMERCIAL = rf"[{_LETRA_COM}][{_LETRA_COM} &'().,o/+°-]{{1,}}"

# ---------------------------------------------------------------- credenciales
RE_USUARIO = re.compile(r"^[a-z0-9._-]{4,30}$")
PATRON_USUARIO = r"[a-z0-9._-]{4,30}"

# ---------------------------------------------------------------- documentos y contacto
RE_DOCUMENTO = re.compile(r"^[0-9A-Za-z]{8,12}$")
PATRON_DOCUMENTO = r"[0-9A-Za-z]{8,12}"

RE_SOLO_DIGITOS = re.compile(r"^\d{6,20}$")
PATRON_SOLO_DIGITOS = r"\d{6,20}"

RE_TELEFONO = re.compile(r"^[0-9+][0-9+\s()-]{5,19}$")
PATRON_TELEFONO = r"[0-9+][0-9+\s()-]{5,19}"

RE_RUC = re.compile(r"^\d{11}$")
PATRON_RUC = r"\d{11}"


def limpiar(valor):
    """Colapsa espacios repetidos y recorta los extremos."""
    return " ".join((valor or "").split())


def validar_nombre(valor, etiqueta="El nombre"):
    """Valida un nombre propio: solo letras y separadores. Devuelve el valor limpio."""
    valor = limpiar(valor)
    if len(valor) < 2:
        raise ValidationError(f"{etiqueta} debe tener al menos 2 letras.")
    if not RE_NOMBRE.match(valor):
        raise ValidationError(
            f"{etiqueta} solo puede contener letras, espacios, apóstrofos, puntos y guiones."
        )
    return valor


def validar_nombre_comercial(valor, etiqueta="El nombre"):
    """Valida un nombre comercial (producto/categoría/negocio). Devuelve el valor limpio."""
    valor = limpiar(valor)
    if len(valor) < 2:
        raise ValidationError(f"{etiqueta} debe tener al menos 2 caracteres.")
    if not RE_NOMBRE_COMERCIAL.match(valor):
        raise ValidationError(f"{etiqueta} contiene caracteres no permitidos.")
    return valor


def validar_documento(valor, etiqueta="El documento"):
    """Valida un documento de identidad alfanumérico de 8 a 12 caracteres."""
    valor = (valor or "").strip()
    if not valor:
        return ""
    if not RE_DOCUMENTO.match(valor):
        raise ValidationError(f"{etiqueta} debe tener entre 8 y 12 caracteres alfanuméricos.")
    return valor


def validar_telefono(valor, etiqueta="El teléfono"):
    """Valida un teléfono flexible (números, +, espacios, paréntesis y guiones)."""
    valor = (valor or "").strip()
    if not valor:
        return ""
    if not RE_TELEFONO.match(valor):
        raise ValidationError(f"{etiqueta} solo admite números, +, espacios, paréntesis y guiones.")
    return valor


def validar_ruc(valor, etiqueta="El RUC"):
    valor = (valor or "").strip()
    if not valor:
        return ""
    if not RE_RUC.match(valor):
        raise ValidationError(f"{etiqueta} debe tener 11 dígitos.")
    return valor


def validar_solo_digitos(valor, etiqueta="El número", minimo=6, maximo=20):
    valor = (valor or "").strip()
    if not valor:
        return ""
    if not valor.isdigit() or not (minimo <= len(valor) <= maximo):
        raise ValidationError(f"{etiqueta} debe contener solo números (entre {minimo} y {maximo} dígitos).")
    return valor
