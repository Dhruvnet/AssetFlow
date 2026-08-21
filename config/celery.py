import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("assetflow")

# Read CELERY_* settings from Django settings.py (CELERY_BROKER_URL etc).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in installed apps (finds inventory/tasks.py).
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "flag-overdue-checkouts-hourly": {
        "task": "inventory.tasks.flag_overdue_checkouts",
        "schedule": crontab(minute=0),  # every hour, on the hour
    },
}