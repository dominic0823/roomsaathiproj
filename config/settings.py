import sys
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

TESTING = "test" in sys.argv

env = environ.Env(DEBUG=(bool, True))
environ.Env.read_env(BASE_DIR / ".env")

LOCAL_MODE = env.bool("LOCAL_MODE", default=False)
DEMO_MODE = env.bool("DEMO_MODE", default=LOCAL_MODE) and not TESTING

SECRET_KEY = env("SECRET_KEY", default="dev-secret-key-change-me")
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

RAILWAY_PUBLIC_DOMAIN = env("RAILWAY_PUBLIC_DOMAIN", default="")
if RAILWAY_PUBLIC_DOMAIN:
    ALLOWED_HOSTS.append(RAILWAY_PUBLIC_DOMAIN)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if RAILWAY_PUBLIC_DOMAIN:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RAILWAY_PUBLIC_DOMAIN}")
RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.sitemaps",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "accounts",
    "services",
    "bookings",
    "chatapp",
    "pages",
    "payments",
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

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.notifications",
                "services.context_processors.compare_tray",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if LOCAL_MODE and not env("DATABASE_URL", default=""):
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    DATABASES = {
        "default": env.db(
            "DATABASE_URL",
            default=f"postgres://{env('DB_USER', default='marketplace_user')}:"
            f"{env('DB_PASSWORD', default='marketplace_pass')}@"
            f"{env('DB_HOST', default='127.0.0.1')}:"
            f"{env('DB_PORT', default='5432')}/"
            f"{env('DB_NAME', default='marketplace_db')}",
        )
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

if TESTING:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

USE_OBJECT_STORAGE = bool(env("AWS_STORAGE_BUCKET_NAME", default=""))
if USE_OBJECT_STORAGE:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
            "access_key": env("AWS_ACCESS_KEY_ID", default=""),
            "secret_key": env("AWS_SECRET_ACCESS_KEY", default=""),
            "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=None),
            "region_name": env("AWS_S3_REGION_NAME", default=None),
            "custom_domain": env("AWS_S3_CUSTOM_DOMAIN", default=None),
            "querystring_auth": False,
            "file_overwrite": False,
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}
if TESTING or LOCAL_MODE:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_ALWAYS_EAGER = TESTING or LOCAL_MODE
CELERY_BEAT_SCHEDULE = {
    "expire-pending-bookings": {
        "task": "bookings.tasks.expire_pending_bookings",
        "schedule": 60.0,
    },
}

OTP_PROVIDER = env("OTP_PROVIDER", default="local").strip().lower()
TWILIO_VERIFY_SERVICE_SID = env("TWILIO_VERIFY_SERVICE_SID", default="").strip()
REQUIRE_PHONE_VERIFICATION = env.bool("REQUIRE_PHONE_VERIFICATION", default=DEMO_MODE or not LOCAL_MODE) or TESTING
OTP_SMS_BACKEND = env("OTP_SMS_BACKEND", default="console").strip().lower()
OTP_WHATSAPP_BACKEND = env("OTP_WHATSAPP_BACKEND", default="console").strip().lower()
OTP_EXPIRY_MINUTES = env.int("OTP_EXPIRY_MINUTES", default=5)
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)
OTP_RESEND_SECONDS = env.int("OTP_RESEND_SECONDS", default=30)
OTP_MAX_PER_HOUR = env.int("OTP_MAX_PER_HOUR", default=5)
OTP_DEV_ECHO = env.bool("OTP_DEV_ECHO", default=DEBUG) and not TESTING
TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN", default="")
TWILIO_FROM_NUMBER = env("TWILIO_FROM_NUMBER", default="")
TWILIO_MESSAGING_SERVICE_SID = env("TWILIO_MESSAGING_SERVICE_SID", default="")
TWILIO_WHATSAPP_FROM = env("TWILIO_WHATSAPP_FROM", default="whatsapp:+14155238886")
TWILIO_WHATSAPP_CONTENT_SID = env("TWILIO_WHATSAPP_CONTENT_SID", default="")
META_WA_TOKEN = env("META_WA_TOKEN", default="")
META_WA_PHONE_NUMBER_ID = env("META_WA_PHONE_NUMBER_ID", default="")
META_WA_TEMPLATE_NAME = env("META_WA_TEMPLATE_NAME", default="")
META_WA_TEMPLATE_LANG = env("META_WA_TEMPLATE_LANG", default="en")
META_WA_AUTH_TEMPLATE = env.bool("META_WA_AUTH_TEMPLATE", default=True)
META_WA_GRAPH_VERSION = env("META_WA_GRAPH_VERSION", default="v20.0")

RENTAL_REQUEST_HOURS = env.int("RENTAL_REQUEST_HOURS", default=48)
RENTAL_PAYMENT_HOURS = env.int("RENTAL_PAYMENT_HOURS", default=24)
RENTAL_REFUND_DAYS_BEFORE_MOVE_IN = env.int("RENTAL_REFUND_DAYS_BEFORE_MOVE_IN", default=3)

PENDING_BOOKING_MINUTES = env.int("PENDING_BOOKING_MINUTES", default=15)

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend").strip()
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="RoomSaathi <no-reply@roomsaathi.local>")

RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="rzp_test_key")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="rzp_test_secret")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "180/min"},
}

PAYMENT_MODE = env("PAYMENT_MODE", default="razorpay").strip().lower()

if DEMO_MODE:
    PAYMENT_MODE = "demo"
    OTP_PROVIDER = "local"
    OTP_SMS_BACKEND = "console"
    OTP_WHATSAPP_BACKEND = "console"
    OTP_DEV_ECHO = True
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
