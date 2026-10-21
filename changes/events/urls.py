from django.urls import path

from . import api, views

app_name = "events"

urlpatterns = [
    path("days/", views.days_page, name="days"),
    path("ring/<str:src>/<str:boot_id>/<int:first_seq>/", views.ring_page,
         name="ring"),
    path("api/since/", api.since, name="api_since"),
    path("api/days/", api.days, name="api_days"),
]
