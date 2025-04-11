from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]


# ================================ SUPERUSER =======================================
ADMIN_USERNAME = config("ADMIN_USERNAME")
ADMIN_EMAIL = config("ADMIN_EMAIL")
ADMIN_PASSWORD = config("ADMIN_PASSWORD")
# ================================ SUPERUSER =======================================


# ================================ DATABASES =======================================
raw_db_url = config("DATABASE_URL", default="sqlite:///db.sqlite3")
DATABASES = {"default": dj_database_url.parse(raw_db_url or "sqlite:///db.sqlite3")}

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


# ================================ REDIS =======================================
REDIS_HOST = "redis"
REDIS_PORT = 6379
# Choose a database number for this specific temporary storage
# Avoid using DB 0 if your main cache or Celery broker uses it
REDIS_DB_TEMP_FLOORPLANS = 1
# Time-to-live for the stored original floorplan data (e.g., 1 day = 86400 seconds)
# Adjust based on how long your analysis task might reasonably take + buffer
REDIS_TEMP_FLOORPLANS_TTL = 86400
# ================================ REDIS =======================================
