"""Celery application for manga_downloader."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "manga_downloader.settings")

app = Celery("manga_downloader")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

