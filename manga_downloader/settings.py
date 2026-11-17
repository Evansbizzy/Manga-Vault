import os
from pathlib import Path
from urllib.parse import unquote, urlparse
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent



def _env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name, default):
    value = os.getenv(name)
    return [item.strip() for item in value.split(',') if item.strip()] if value else default


DEBUG = _env_bool('DJANGO_DEBUG', True)
DEVELOPMENT_SECRET_KEY = 'local-development-secret-key-change-this-before-deploying-please'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', DEVELOPMENT_SECRET_KEY)
if not DEBUG and SECRET_KEY in {'', DEVELOPMENT_SECRET_KEY, 'replace-this-with-a-long-random-secret'}:
    raise ImproperlyConfigured('Set a unique DJANGO_SECRET_KEY before running with DJANGO_DEBUG=false.')
ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', ['127.0.0.1', 'localhost'])
if not DEBUG and '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Wildcard DJANGO_ALLOWED_HOSTS is not allowed in production.')
SITE_URL = os.getenv('DJANGO_SITE_URL', '').rstrip('/')
SITE_CONTACT_EMAIL = os.getenv('SITE_CONTACT_EMAIL', '').strip()

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'core',
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'manga_downloader.middleware.ProductionLoginRequiredMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'manga_downloader.urls'

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
                'manga_downloader.context_processors.site_url',
            ],
        },
    },
]

WSGI_APPLICATION = 'manga_downloader.wsgi.application'

database_url = os.getenv('DATABASE_URL', '').strip()
if database_url.startswith(('postgres://', 'postgresql://')):
    parsed_database_url = urlparse(database_url)
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed_database_url.path.lstrip('/')),
        'USER': unquote(parsed_database_url.username or ''),
        'PASSWORD': unquote(parsed_database_url.password or ''),
        'HOST': parsed_database_url.hostname or '',
        'PORT': parsed_database_url.port or '',
        'CONN_MAX_AGE': 60,
        'OPTIONS': {'sslmode': os.getenv('DATABASE_SSLMODE', 'prefer')},
    }}
elif database_url.startswith('sqlite:///'):
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': unquote(database_url.removeprefix('sqlite:///')),
    }}
elif database_url:
    raise ImproperlyConfigured('DATABASE_URL must use postgres://, postgresql://, or sqlite:///')
else:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.getenv('DJANGO_DB_PATH', str(BASE_DIR / 'db.sqlite3')),
    }}

redis_url = os.getenv('REDIS_URL', '').strip()
if redis_url:
    CACHES = {'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': redis_url,
        'KEY_PREFIX': 'mangavault',
        'TIMEOUT': 300,
    }}
else:
    CACHES = {'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'mangavault-local',
        'TIMEOUT': 300,
    }}

ALLOW_LOCAL_TASK_FALLBACK = _env_bool('ALLOW_LOCAL_TASK_FALLBACK', DEBUG)

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR / 'media'))).resolve()

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '36000/hour',
        'user': '36000/hour',
        'search': '20/minute',
        'import': '20/hour',
        'download': '60/hour',
        'proxy_image': '20000/hour',
        'progress': '120/minute',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}

CORS_ALLOWED_ORIGINS = _env_list('CORS_ALLOWED_ORIGINS', [])

# Download settings
DOWNLOADS_DIR = Path(os.getenv('DOWNLOADS_DIR', str(BASE_DIR / 'downloads'))).resolve()
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_REFERRER_POLICY = 'same-origin'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Celery (for background downloads)
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', redis_url or 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'core.scrapers': {'handlers': ['console'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'), 'propagate': False},
        'api': {'handlers': ['console'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'), 'propagate': False},
    },
}
