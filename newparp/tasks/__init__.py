import os
import raven

from celery import Celery, Task
from classtools import reify
from raven.contrib.celery import register_signal, register_logger_signal

from newparp.model.connections import redis_pool, NewparpRedis

celery = Celery("newparp", include=[
    "newparp.tasks.background",
    "newparp.tasks.matchmaker",
    "newparp.tasks.reaper",
    "newparp.tasks.chat",
    "newparp.tasks.test",
    "newparp.tasks.spamless",
])

# Sentry exception logging if there is a sentry object.
if "SENTRY_PRIVATE_DSN" in os.environ:
    sentry = raven.Client(
        dsn=os.environ["SENTRY_PRIVATE_DSN"],
        include_paths=["newparp"],
    )
    register_logger_signal(sentry)
    register_signal(sentry)

celery.config_from_object('newparp.tasks.config')

class WorkerTask(Task):
    abstract = True

    @reify
    def redis(self):
        return NewparpRedis(connection_pool=redis_pool)

    def after_return(self, *args, **kwargs):
        if hasattr(self, "redis"):
            del self.redis

