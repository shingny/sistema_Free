# En el Sprint 3 este archivo se ampliará con Django Channels (WebSocket).
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()
