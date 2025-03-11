# import django_on_heroku

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["*"]


# ================================ DATABASES =======================================
DATABASES = {"default": dj_database_url.parse(config("DATABASE_URL"))}
# DATABASES["default"]["OPTIONS"] = {"sslmode": "require"}
# ================================ DATABASES =======================================


# ================================ STORAGES =======================================
# ==> AMAZON S3 SETTINGS
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None
AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age-86400"}
AWS_LOCATION = "static"
AWS_QUERYSTRING_AUTH = False
AWS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
}

# ==> MEDIA FILE UPLOADS
PUBLIC_MEDIA_LOCATION = "media"
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{PUBLIC_MEDIA_LOCATION}/"
# DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
DEFAULT_FILE_STORAGE = f"{config('PROJECT_NAME')}.config.storage_backends.MediaStorage"

# ==> STATIC FILE UPLOADS
STATICFILES_STORAGE = "storages.backends.s3boto3.S3StaticStorage"
STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/"
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
CELERY_IMPORTS = (f"{config('PROJECT_NAME')}.tasks",)

# If using JSON as the serialization format
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# CELERY_TASK_QUEUES = {
#     "analysis_queue": {
#         "exchange": "analysis_exchange",
#         "routing_key": "analysis.#",
#     },
# }
# ================================ CELERY =======================================

# MY_DOMAIN = "http://analysis-app:8000"

# ================================ HEROKU =======================================
# # ==> HEROKU LOGGING
# DEBUG_PROPAGATE_EXCEPTIONS = True
# LOGGING = {
#     "version": 1,
#     "disable_existing_loggers": False,
#     "formatters": {
#         "verbose": {
#             "format": "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
#             "datefmt": "%d/%b/%Y %H:%M:%S",
#         },
#         "simple": {
#             "format": "[%(asctime)s] %(levelname)s %(message)s",
#         },
#     },
#     "handlers": {
#         "console": {
#             "level": "DEBUG",
#             "class": "logging.StreamHandler"
#         }
#     },
#     "loggers": {
#         "dfxapp": {
#             "handlers": ["console"],
#             "level": "INFO",
#         },
#     },
# }

# # ==> HEROKU DATABASE
# django_on_heroku.settings(locals(), staticfiles=False)
# del DATABASES["default"]["OPTIONS"]["sslmode"]
# ================================ HEROKU =======================================


# ================================ SSL CONFIG =======================================
# # Force SSL redirect if site is live
# if os.getcwd() == '/app':ls

#     SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
#     SECURE_SSL_REDIRECT = True
#     # DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
# ================================ SSL CONFIG =======================================
