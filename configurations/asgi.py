"""ASGI entry point. Servers import ``application`` from here.

Uses production settings unless DJANGO_SETTINGS_MODULE says otherwise.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "configurations.settings.production")

application = get_asgi_application()
