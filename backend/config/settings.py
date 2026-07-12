import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

from kalshi_api.auth import load_local_env


load_local_env(BASE_DIR)

SECRET_KEY = "dev-only-kalshi-clone-secret-key"
# Render sets RENDER=true on every deployed service automatically — no dashboard
# config needed. Keeps DEBUG on for local dev, off for the live deployment so a
# transient exception on any route returns a small error page instead of
# Django's full HTML traceback (which is what tripped the cron monitor's
# response-size limit on /ping/).
DEBUG = not bool(os.environ.get("RENDER"))
ALLOWED_HOSTS = ["localhost", "127.0.0.1","secondclone-67mh.onrender.com" ,".onrender.com", ".vercel.app"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "kalshi_api.apps.KalshiApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = []
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
