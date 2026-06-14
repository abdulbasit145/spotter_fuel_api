"""Production settings: PostgreSQL, WhiteNoise static serving, hardened.

Required environment variables:

* ``DJANGO_SECRET_KEY`` -- the Django secret key.
* ``DJANGO_ALLOWED_HOSTS`` -- comma-separated list of allowed hosts.
* ``DATABASE_URL`` -- a PostgreSQL connection URL.
"""
import dj_database_url

from config.settings.base import *  # noqa: F401, F403

DEBUG = False

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']  # noqa: F405

ALLOWED_HOSTS = os.environ['DJANGO_ALLOWED_HOSTS'].split(',')  # noqa: F405

DATABASES = {
    'default': dj_database_url.config(
        env='DATABASE_URL',
        conn_max_age=600,
        conn_health_checks=True,
    ),
}

MIDDLEWARE.insert(  # noqa: F405
    1, 'whitenoise.middleware.WhiteNoiseMiddleware',
)

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

REDIS_URL = os.environ.get('REDIS_URL')  # noqa: F405
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        },
    }

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'True') == 'True'  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
