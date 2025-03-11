import os

from celery import Celery
from decouple import config
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", config("DJANGO_SETTINGS_MODULE"))

app = Celery("floorplan_service")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object("django.conf:settings", namespace="CELERY")

# # Set default queue
# app.conf.task_default_queue = "floorplan_queue"

# # Load task modules from all registered Django app configs.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# app.autodiscover_tasks()
app.conf.broker_url = settings.CELERY_BROKER_URL


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
