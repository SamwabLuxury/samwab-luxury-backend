"""WSGI entry point. Servers import ``application`` from here.

Uses production settings unless DJANGO_SETTINGS_MODULE says otherwise.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "configurations.settings.production")

application = get_wsgi_application()
