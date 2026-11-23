"""Settings for the live site (Render, with the database on Neon).

Everything sensitive comes from environment variables, set in Render's dashboard.
"""

from typing import Any

from django.core.exceptions import ImproperlyConfigured

from apps.core.encryption import LOCAL_ONLY_ENCRYPTION_KEY

from .base import *
from .base import env

DEBUG = False

# ---------- Encrypted columns ----------
# Keep these keys safe: without them, addresses cannot be read. Make one with
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEYS = env.list("DJANGO_FIELD_ENCRYPTION_KEYS", default=[])
if not FIELD_ENCRYPTION_KEYS or LOCAL_ONLY_ENCRYPTION_KEY in FIELD_ENCRYPTION_KEYS:
    raise ImproperlyConfigured(
        "Set DJANGO_FIELD_ENCRYPTION_KEYS to a key of the live site's own "
        "(not the local-only key in apps/core/encryption.py)."
    )

# ---------- Payments ----------
# The live site always uses Stripe, with keys from Render's environment.
PAYMENT_PROVIDER = "stripe"
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
if not STRIPE_SECRET_KEY.startswith(("sk_", "rk_")) or not STRIPE_WEBHOOK_SECRET.startswith(
    "whsec_"
):
    raise ImproperlyConfigured(
        "Set STRIPE_SECRET_KEY (sk_test_... in the sandbox) and STRIPE_WEBHOOK_SECRET "
        "(whsec_...) in Render's environment."
    )

# ---------- Database: Neon PostgreSQL ----------
# DATABASE_URL is Neon's *pooled* connection string (its host contains "-pooler").
# Migrations use the direct string instead; Render's build command passes it.
# The options follow Neon's Django guide.
_database: dict[str, Any] = dict(env.db("DATABASE_URL"))
_options: dict[str, Any] = dict(_database.get("OPTIONS", {}))
_options.setdefault("sslmode", "require")  # encrypted, unless the address asks for stricter
DATABASES = {
    "default": {
        **_database,
        "OPTIONS": _options,
        # Neon's pooler is PgBouncer in transaction mode: no server-side cursors.
        "DISABLE_SERVER_SIDE_CURSORS": True,
        # Neon suspends idle computes after 5 minutes, which closes connections.
        "CONN_MAX_AGE": 300,
        "CONN_HEALTH_CHECKS": True,
    }
}

# ---------- Addresses ----------
# Render sets RENDER_EXTERNAL_HOSTNAME (for example samwab-api.onrender.com).
# DJANGO_ALLOWED_HOSTS and DJANGO_CSRF_TRUSTED_ORIGINS add others, such as a custom domain.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
RENDER_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOSTNAME}")

# ---------- Static files ----------
# Compressed, with hashed names so browsers can cache them for ever (WhiteNoise docs).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------- Email ----------
# Until an email service is chosen, DJANGO_EMAIL_TO_LOGS=true writes every email
# (such as sign-up codes) to Render's logs instead of sending it. Demo only.
EMAIL_TO_LOGS = env.bool("DJANGO_EMAIL_TO_LOGS", default=False)
if EMAIL_TO_LOGS:
    MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}

# ---------- HTTPS ----------
# Render terminates HTTPS and forwards requests to Django.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
# The host's health check calls this path over plain HTTP.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
X_FRAME_OPTIONS = "DENY"
# Not on the browsers' HSTS preload list: that is hard to undo, and *.onrender.com
# cannot be preloaded. Decide again when Samwab has its own domain.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
if EMAIL_TO_LOGS:
    # Django 6.1 refuses a development email backend in production (mail.E001).
    # Emails to the logs are a deliberate, temporary choice for the demo.
    SILENCED_SYSTEM_CHECKS.append("mail.E001")
