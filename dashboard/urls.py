from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),

    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="dashboard/login.html"
        ),
        name="login",
    ),

    path(
        "requests/<int:request_id>/",
        views.request_detail,
        name="request_detail",
    ),
]
