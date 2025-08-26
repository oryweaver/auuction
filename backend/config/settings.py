import os
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

environ.Env.read_env(os.path.join(BASE_DIR.parent, '.env'))

DEBUG = env('DEBUG')
SECRET_KEY = env('DJANGO_SECRET_KEY', default='insecure-dev-key')
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'accounts.apps.AccountsConfig',
    'auctions',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': env.db('DATABASE_URL', default='sqlite:///db.sqlite3')
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://127.0.0.1:6379/1'),
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=25)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='auuction <noreply@localhost>')

# CSRF trusted origins for local development and browser previews
CSRF_TRUSTED_ORIGINS = env.list(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    default=[
        'http://localhost',
        'http://127.0.0.1',
        'http://localhost:8080',
        'http://127.0.0.1:8080',
        'http://127.0.0.1:34763',
    ],
)

# Celery
CELERY_BROKER_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/1')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# Auth settings
AUTHENTICATION_BACKENDS = [
    'auctions.auth_backends.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
]
LOGIN_URL = 'auctions:login'
LOGIN_REDIRECT_URL = 'auctions:catalog_list'
LOGOUT_REDIRECT_URL = 'auctions:catalog_list'

# Custom user model (email as username)
AUTH_USER_MODEL = 'accounts.User'

