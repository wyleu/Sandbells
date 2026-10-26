from django.urls import path

from . import views

app_name = "sandtest"

urlpatterns = [
    path("sandtest/", views.page, name="page"),
    path("sandtest/status", views.status, name="status"),
    path("sandtest/cmd", views.cmd, name="cmd"),
]
