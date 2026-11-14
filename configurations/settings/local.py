"""Settings for a developer's own machine."""

from copy import deepcopy

from .base import *
from .base import LOGGING as BASE_LOGGING
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

# Plain text logs are easier to read in a terminal than JSON.
LOGGING = deepcopy(BASE_LOGGING)
LOGGING["handlers"]["console"]["formatter"] = "plain"
