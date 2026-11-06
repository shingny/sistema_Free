from django.core.paginator import Paginator


def paginar(request, queryset, por_pagina=15):
    pagina = Paginator(queryset, por_pagina).get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return pagina, parametros.urlencode()
