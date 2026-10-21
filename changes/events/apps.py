from django.apps import AppConfig
from django.db.backends.signals import connection_created


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "events"
    verbose_name = "Sand events"

    def ready(self):
        from .db import on_connection_created
        connection_created.connect(on_connection_created,
                                   dispatch_uid="events.sqlite_pragmas")
