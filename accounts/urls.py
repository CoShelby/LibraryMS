from django.contrib.auth import views as auth_views
from django.urls import path

from .forms import AdminAuthenticationForm

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="public/login.html",
            authentication_form=AdminAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="home"), name="logout"),
]
