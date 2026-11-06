from decimal import Decimal, InvalidOperation

from django import template

from apps.nucleo.auditoria import ETIQUETAS_ACCION

register = template.Library()


@register.filter
def soles(valor):
    try:
        return f"S/ {Decimal(valor):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "S/ 0.00"


@register.filter
def etiqueta_accion(codigo):
    return ETIQUETAS_ACCION.get(codigo, codigo)
