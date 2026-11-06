from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.static import serve

urlpatterns = [
    path("", include("apps.nucleo.urls")),
    path("", include("apps.cuentas.urls")),
    path("", include("apps.catalogo.urls")),
    path("caja/", include("apps.ventas.urls_caja")),
    path("cocina/", include("apps.cocina.urls")),
    path("mesero/", include("apps.ventas.urls_mesero")),
    path("", include("apps.ventas.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Render y Alwaysdata no sirven /media/ por sí solos. Las imágenes de
    # productos/logo se versionan en media/ y Django las atiende aquí.
    urlpatterns += [
        path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
