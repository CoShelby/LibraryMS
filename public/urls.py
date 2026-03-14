from django.urls import path

from .views import home_view, search_results_view

urlpatterns = [
    path("", home_view, name="home"),
    path("search/", search_results_view, name="search_results"),
]
