from __future__ import absolute_import

import os

from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tickerbot.settings')

app = Celery('tickerbot')


# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'performance_update': {
        'task': 'insights.tasks.send_performance_updates',
        'schedule': crontab(hour=7, minute=30, day_of_week='1-5')
        # 'schedule': 10.0
    },
    'update_user_list': {
        'task': 'insights.tasks.update_user_list',
        'schedule': crontab(hour=3, minute=30)
        # 'schedule': 10.0
    },
}
app.conf.update(
    CELERY_TASK_RESULT_EXPIRES=3600
)
