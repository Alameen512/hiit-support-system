"""Settings for HIIT Support. All secrets come from environment variables."""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


DEBUG = env_bool("DEBUG", True)

SECRET_KEY = os.environ.get("SECRET_KEY")

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "insecure-local-development-key"
    else:
        SECRET_KEY = "temporary-build-placeholder-change-me"
# --- Hosts / CSRF -----------------------------------------------------------
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
# Vercel injects these automatically; trust them so previews/production work.
for _h in (os.environ.get("VERCEL_URL"), os.environ.get("VERCEL_PROJECT_PRODUCTION_URL"),
           os.environ.get("VERCEL_BRANCH_URL")):
    if _h:
        ALLOWED_HOSTS.append(_h)
        CSRF_TRUSTED_ORIGINS.append(f"https://{_h}")
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set when DEBUG is off.")

# --- Apps -------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "support",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "support.context.roles",
    ]},
}]

# --- Database ---------------------------------------------------------------
# Production: DATABASE_URL pointing at Neon/Postgres. Local dev: SQLite fallback.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    _is_sqlite = DATABASE_URL.startswith("sqlite")
    DATABASES = {"default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=0,  # serverless: don't keep connections between invocations
        ssl_require=not DEBUG and not _is_sqlite,
    )}
    if not _is_sqlite:
        # Needed when the URL goes through a pooler such as Neon's pgbouncer.
        DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
elif DEBUG:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    raise ImproperlyConfigured("DATABASE_URL must be set when DEBUG is off (SQLite is not used in production).")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Auth / sessions --------------------------------------------------------
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "landing"
SESSION_ENGINE = "django.contrib.sessions.backends.db"  # sessions live in PostgreSQL
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7

# --- i18n -------------------------------------------------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

# --- Static files -----------------------------------------------------------
# WhiteNoise serves files straight from /static (USE_FINDERS) so no build step
# is required on Vercel. `collectstatic` still works for other hosts.
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# --- Security ---------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True

# --- Django REST Framework --------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle",
                                 "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/min", "user": "120/min"},
    "EXCEPTION_HANDLER": "support.api_views.exception_handler",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
