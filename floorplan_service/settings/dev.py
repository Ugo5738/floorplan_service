from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]


# ================================ SUPERUSER =======================================
ADMIN_USERNAME = config("ADMIN_USERNAME")
ADMIN_EMAIL = config("ADMIN_EMAIL")
ADMIN_PASSWORD = config("ADMIN_PASSWORD")
# ================================ SUPERUSER =======================================


# ================================ DATABASES =======================================
# Get the URL from environment variable or default to SQLite
# Ensure a sensible default for local dev if DATABASE_URL isn't set
default_db_url = config("DATABASE_URL", default=None)
if not default_db_url:
    # Construct a default SQLite path relative to BASE_DIR if not set
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_db_url = f"sqlite:///{os.path.join(BASE_DIR, 'db.sqlite3')}"
    print(f"WARNING: DATABASE_URL not set, using default SQLite: {default_db_url}")

DATABASES = {"default": dj_database_url.parse(default_db_url)}

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": BASE_DIR / "db.sqlite3",
#     }
# }


# --- Temporary Restore Database (PostgreSQL) ---
TEMP_RESTORE_DB_NAME = config(
    "TEMP_RESTORE_DB_NAME", default="floorplandb_temp_restore"
)
TEMP_RESTORE_DB_USER = config(
    "TEMP_RESTORE_DB_USER", default="danai"
)  # User with access
TEMP_RESTORE_DB_PASSWORD = config("TEMP_RESTORE_DB_PASSWORD", default="")
TEMP_RESTORE_DB_HOST = config("TEMP_RESTORE_DB_HOST", default="localhost")
TEMP_RESTORE_DB_PORT = config("TEMP_RESTORE_DB_PORT", default="5432")

# Only add the temp DB config if essential details are provided
if TEMP_RESTORE_DB_NAME and TEMP_RESTORE_DB_USER:  # Add PASSWORD check if required
    DATABASES["temp_restore"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": TEMP_RESTORE_DB_NAME,
        "USER": TEMP_RESTORE_DB_USER,
        "PASSWORD": TEMP_RESTORE_DB_PASSWORD,
        "HOST": TEMP_RESTORE_DB_HOST,
        "PORT": TEMP_RESTORE_DB_PORT,
        "TEST": {
            # Prevent Django from trying to manage this DB during tests
            # Often mirroring 'default' or setting 'SERIALIZE': False is needed
            "MIRROR": "default",
        },
        # Optional: Add connection options if needed
        # 'OPTIONS': {
        #     'connect_timeout': 5,
        # }
    }
    print(f"INFO: Temporary restore database '{TEMP_RESTORE_DB_NAME}' configured.")
else:
    print(
        "WARNING: Temporary restore database configuration skipped (missing NAME or USER)."
    )
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
