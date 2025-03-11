from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]


# ================================ SUPERUSER =======================================
ADMIN_USERNAME = config("ADMIN_USERNAME")
ADMIN_EMAIL = config("ADMIN_EMAIL")
ADMIN_PASSWORD = config("ADMIN_PASSWORD")
# ================================ SUPERUSER =======================================


# ================================ DATABASES =======================================
DATABASES = {
    "default": dj_database_url.config(default="sqlite:///db.sqlite3", conn_max_age=600)
}

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }
# ================================ DATABASES =======================================


# ================================ STORAGES =======================================
# ==> STATIC FILE UPLOADS
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

# ==> MEDIA FILE UPLOADS
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# ================================ STORAGES =======================================


# ================================ REDIS/CHANNELS =======================================
# CACHES = {
#     "default": {
#         "BACKEND": "django_redis.cache.RedisCache",
#         "LOCATION": config("REDIS_URL"),
#         "OPTIONS": {
#             "CLIENT_CLASS": "django_redis.client.DefaultClient",
#         }
#     }
# }

# ==> CHANNELS
default_channel_layer = {
    "BACKEND": "channels_redis.core.RedisChannelLayer",
    "CONFIG": {
        "hosts": [config("REDIS_URL")],  # , 'redis://127.0.0.1:6379')],
    },
}
CHANNEL_LAYERS = {"default": default_channel_layer}
# ================================ REDIS =======================================


# ================================ CELERY =======================================
# Use the actual IP address and port of your Redis server
CELERY_BROKER_URL = config("REDIS_URL")
CELERY_RESULT_BACKEND = config("REDIS_URL")
CELERY_TIMEZONE = "UTC"

# List of modules to import when the Celery worker starts.
CELERY_IMPORTS = ("floorplan_service.tasks",)

# If using JSON as the serialization format
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
# ================================ CELERY =======================================
