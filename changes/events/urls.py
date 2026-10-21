from django.urls import path

from . import api

app_name = "events"

urlpatterns = [
    path("api/since/", api.since, name="api_since"),
    path("api/days/", api.days, name="api_days"),
]
