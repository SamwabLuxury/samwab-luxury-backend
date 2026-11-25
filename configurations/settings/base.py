"""Settings shared by every environment.

Do not point Django at this file. Use local, test, staging or production,
which all start from here and change only what differs.
"""

from pathlib import Path
from typing import Any

import environ

# Repo root: configurations/settings/base.py -> three levels up.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Values come from environment variables. Locally they are read from .env.
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")

# Keys for encrypted columns such as addresses (apps/platform/core/encryption.py), comma-separated.
# The first key encrypts; every key decrypts. Separate from SECRET_KEY on purpose.
FIELD_ENCRYPTION_KEYS = env.list("DJANGO_FIELD_ENCRYPTION_KEYS", default=[])

# Payments (apps/money/payments). "stripe", or "fake" in tests. Keys from the Stripe
# dashboard: the secret key (sk_test_ in the sandbox) and the webhook signing
# secret (whsec_). Never in Git.
PAYMENT_PROVIDER = env("DJANGO_PAYMENT_PROVIDER", default="stripe")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "allauth",
    "apps.users.accounts.allauth_config.EmailAddressesConfig",  # allauth.account, renamed
    "allauth.headless",
    "allauth.mfa",  # two-step login: authenticator app codes and recovery codes (build 06)
]
LOCAL_APPS = [
    "apps.platform.core",
    "apps.users.accounts",
    "apps.platform.audit",
    "apps.platform.idempotency",
    "apps.inventory.catalog",
    "apps.inventory.pieces",
    "apps.shop.listings",
    "apps.users.addresses",
    "apps.users.mailing_list",
    "apps.money.payments",
    "apps.shop.orders",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    # First in the list, so the request ID exists before anything else runs.
    "apps.platform.core.request_id.RequestIdMiddleware",
    # The caller's IP address, for the audit log.
    "apps.platform.core.client_ip.ClientIpMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Serves the admin's CSS and JavaScript on the live site (WhiteNoise docs: right here).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    # Every staff member passes the second step before any admin page (build 06).
    "apps.users.accounts.middleware.AdminTwoStepMiddleware",
]

ROOT_URLCONF = "configurations.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Our own templates. Today: the wording of allauth's emails.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "configurations.wsgi.application"

# Local database for now. Build 01 decides the real database setup.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Our own user model: people log in with their email. See apps/users/accounts/models.py.
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    # The admin site logs in with Django's own backend.
    "django.contrib.auth.backends.ModelBackend",
    # Sign-up and login for the web app go through django-allauth.
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Argon2 is the password hash the data model specifies. The others stay listed
# so that any password saved with them can still be checked, then upgraded.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# A CSRF failure on an API path answers in the API's error format.
CSRF_FAILURE_VIEW = "apps.platform.core.api.errors.csrf_failure"

# ---------- Sign-up and login (django-allauth, headless) ----------
# The web app calls allauth's JSON API under /_allauth/browser/v1/. allauth
# serves no pages of its own. Its responses and errors use allauth's format.
HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
HEADLESS_SERVE_SPECIFICATION = True  # allauth's own API description at /_allauth/openapi.html

ACCOUNT_ADAPTER = "apps.users.accounts.adapter.AccountAdapter"
ACCOUNT_SIGNUP_FORM_CLASS = "apps.users.accounts.forms.SignupForm"
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]

# A new account must confirm her email with a 6-digit code before she can log in.
# Password reset also uses a 6-digit code. ALLAUTH_USER_CODE_FORMAT is the documented
# setting for every code allauth sends, so one value covers both.
ALLAUTH_USER_CODE_FORMAT = {"numeric": True, "length": 6, "dashed": False}
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
ACCOUNT_PASSWORD_RESET_BY_CODE_ENABLED = True

ACCOUNT_EMAIL_SUBJECT_PREFIX = "Samwab: "

# ---------- Two-step login (allauth.mfa, build 06) ----------
# An authenticator app's 6-digit code (TOTP) or one of 10 one-time recovery codes,
# after the password. Passkeys stay off until the team asks for them.
# Staff must use it: apps/users/accounts/middleware.py guards every admin page.
MFA_ADAPTER = "apps.users.accounts.mfa_adapter.MFAAdapter"  # stores app keys encrypted
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "Samwab"  # the name shown in the authenticator app

# Links inside allauth's emails point at these web-app pages.
FRONTEND_URL = env("DJANGO_FRONTEND_URL", default="http://localhost:3000")
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/account/verify-email/{{key}}",
    "account_reset_password": f"{FRONTEND_URL}/account/password/reset",
    "account_reset_password_from_key": f"{FRONTEND_URL}/account/password/reset/key/{{key}}",
    "account_signup": f"{FRONTEND_URL}/account/signup",
}
# The web app's pages for the mailing list's emailed links (build E12). The page
# sends the token to POST /api/v1/mailing-list/confirm/ or .../unsubscribe/.
MAILING_LIST_CONFIRM_URL = f"{FRONTEND_URL}/mailing-list/confirm/{{token}}"
MAILING_LIST_UNSUBSCRIBE_URL = f"{FRONTEND_URL}/mailing-list/unsubscribe/{{token}}"
MAILING_LIST_CONFIRM_DAYS = 7
DROP_PAGE_URL = f"{FRONTEND_URL}/drops/{{number}}"

# ---------- Email ----------
# Django 6.1 sends email through MAILERS. Servers use SMTP with these variables;
# a developer's machine prints emails in the terminal (see local.py).
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("DJANGO_EMAIL_HOST", default="localhost"),
            "port": env.int("DJANGO_EMAIL_PORT", default=587),
            "username": env("DJANGO_EMAIL_USER", default=""),
            "password": env("DJANGO_EMAIL_PASSWORD", default=""),
            "use_tls": env.bool("DJANGO_EMAIL_USE_TLS", default=True),
        },
    },
}
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="Samwab <no-reply@samwab.local>")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# `collectstatic` copies every static file here at deploy time; WhiteNoise serves them.
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded files (piece photos). With CLOUDINARY_URL set (in .env), they go to
# Cloudinary, in PHOTO_FOLDER; without it, to the media/ folder on your machine.
# The live site always uses Cloudinary (production.py).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
CLOUDINARY_URL = env("CLOUDINARY_URL", default="")
PHOTO_FOLDER = env("DJANGO_PHOTO_FOLDER", default="samwab/local")
STORAGES = {
    "default": {
        "BACKEND": "apps.platform.core.storage.CloudinaryStorage"
        if CLOUDINARY_URL
        else "django.core.files.storage.FileSystemStorage"
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# The largest photo staff may upload, in bytes.
PHOTO_MAX_BYTES = 20 * 1024 * 1024
# The sizes the API sends for every photo (E7): each fits inside a square of this
# many pixels, never enlarged. thumb: shop cards; medium: the piece page; zoom:
# the "Look closer" viewer. Only on Cloudinary; elsewhere each is the photo itself.
PHOTO_SIZES = {"thumb": 400, "medium": 1200, "zoom": 2400}

# The piece page's "recent sales" (apps/shop/listings/price_explainer.py, build E8):
# comparable sales of the same design and grade from the last COMPARABLE_SALES_DAYS
# days, newest first, at most COMPARABLE_SALES_SHOWN of them.
COMPARABLE_SALES_DAYS = 365
COMPARABLE_SALES_SHOWN = 10

# Delivery choices a buyer may pick at checkout (apps/shop/orders, D49 option A).
# For now only the buyer's own courier; add "keep_in_vault" here to switch it on.
DELIVERY_CHOICES_OFFERED = ["buyer_courier"]

# Save for later (apps/shop/listings, build E11): the most pieces one account may save.
MAX_SAVED_LISTINGS = 200

# Drops (build E13): confirmed mailing-list members see and buy a drop this many hours
# before everyone else.
DROP_EARLY_HOURS = 24

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The API speaks JSON only, and every endpoint needs a logged-in user
# unless the view says otherwise.
REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # Every error uses one format. See apps/platform/core/api/errors.py.
    "EXCEPTION_HANDLER": "apps.platform.core.api.errors.exception_handler",
    # Every list is paged the same way. See apps/platform/core/api/pagination.py.
    "DEFAULT_PAGINATION_CLASS": "apps.platform.core.api.pagination.CursorPagination",
    # Builds the OpenAPI file from the code.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS: dict[str, Any] = {
    "TITLE": "Samwab API",
    "DESCRIPTION": "Back end for Samwab Luxury.",
    "VERSION": "1.0.0",
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # Several models have a "status"; give each list of statuses its own name.
    "ENUM_NAME_OVERRIDES": {
        "OrderStatusEnum": "apps.shop.orders.enums.OrderStatus",
        "ListingStatusEnum": "apps.shop.listings.enums.ListingStatus",
        # One grade list for pieces, filters and the price explainer (build E8).
        "ConditionGradeEnum": "apps.inventory.catalog.enums.ConditionGrade",
        "SaleSourceEnum": "apps.inventory.catalog.enums.SaleSource",
        "AdjustmentDirectionEnum": "apps.shop.listings.enums.AdjustmentDirection",
    },
    "SERVE_INCLUDE_SCHEMA": False,
    # Anyone can read the API description for now. Reviewed in the security build.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}

# Logs go to the console as one JSON object per line, each with the request ID.
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.platform.core.logs.RequestIdFilter"},
    },
    "formatters": {
        "json": {"()": "apps.platform.core.logs.JsonFormatter"},
        "plain": {
            "format": "{levelname} {name} [{request_id}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "json",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Stripe's library logs every request at INFO; keep only its warnings.
        "stripe": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
