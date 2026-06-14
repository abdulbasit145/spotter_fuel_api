"""Development settings: SQLite, debug on, permissive host checks."""
from django.core.management.utils import get_random_secret_key

from config.settings.base import *  # noqa: F401, F403
from config.settings.base import BASE_DIR

DEBUG = True

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY') or get_random_secret_key()  # noqa: F405

ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
