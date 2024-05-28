"""
Django settings for changes project.

Generated by 'django-admin startproject' using Django 4.2.11.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-010iq-lcn9(8y@qh(05*no(_-ntnk-w&j*h^@uj1a1g6-0e81f'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    'testserver',
    'localhost',
    'rasppiseed.local',
    '192.168.0.40',
    '192.168.0.93',
    '192.168.0.120',
    '192.168.43.3',
    '127.0.0.1',
    'rasppidesk.local',
    'zynthian-amp2.local',
    'sandbells.local'
    ]


# Application definition

INSTALLED_APPS = [
    'bells.apps.BellsConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
        # We want our CSP middleware before almost all other middleware since its security
    # related
    "csp.contrib.rate_limiting.RateLimitedCSPMiddleware",
 #   "django_permissions_policy.PermissionsPolicyMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'changes.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'libraries':          {
                'csp': 'csp.templatetags.csp',
            },
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'csp.context_processors.nonce'
            ],
        },
    },
]

WSGI_APPLICATION = 'changes.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ]
}

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-gb'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT ="/var/www/html/static/"

STATICFILES_DIRS = [
    "/home/wyleu/Code/Sandbells/changes/static",
]

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# https://django-csp.readthedocs.io/en/latest/configuration.html
CSP_DEFAULT_SRC = ["'none'"]

CSP_SCRIPT_SRC = ["'self'",
    "http://sandbells.local"
]
CSP_INCLUDE_NONCE_IN = ["script-src"]

CSP_CONNECT_SRC  = ["'self'", 'http://sandbells.local',]
CSP_STYLE_SRC = ["'self'", 'http://sandbells.local',]
CSP_IMG_SRC=["'self'"]
CSP_FRAME_SRC = ["'self'","http://sandbells.local",]
CSP_MEDIA_SRC = ["'self'","http://sandbells.local",]
CSP_FRAME_ANCESTORS = ["'self'","http://sandbells.local",]


# When DEBUG is on we don't require HTTPS on our resources because in a local environment
# we generally don't have access to HTTPS. However, when DEBUG is off, such as in our
# production environment, we want all our resources to load over HTTPS
CSP_UPGRADE_INSECURE_REQUESTS = not DEBUG
# For roughly 60% of the requests to our django server we should include the report URI.
# This helps keep down the number of CSP reports sent from client web browsers
CSP_REPORT_PERCENTAGE = 0.6

# PERMISSIONS_POLICY = {
#     "accelerometer": [],
#     #"ambient-light-sensor": "*",
#     "autoplay": [],
#     "camera": [],
#     "display-capture": [],
#     #"document-domain": "*",
#     "encrypted-media": [],
#     "fullscreen": "*",
#     "geolocation": [],
#     "gyroscope": [],
#     #"interest-cohort": "*",
#     "magnetometer": [],
#     "microphone": [],
#     "midi": ["self", "http://sandbells.local"],
#     "payment": [],
#     "usb": [],
# }
