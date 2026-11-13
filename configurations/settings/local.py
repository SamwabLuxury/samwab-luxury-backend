"""Settings for a developer's own machine."""

from .base import *
from .base import REST_FRAMEWORK as BASE_REST_FRAMEWORK

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Also show DRF's browsable pages locally. They make the API easier to explore.
REST_FRAMEWORK = {
    **BASE_REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
