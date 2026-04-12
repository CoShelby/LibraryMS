from django.urls import path

from .views import home_view, recent_searches_view, search_results_view, search_suggestions_view

urlpatterns = [
    path("", home_view, name="home"),
    path("search/", search_results_view, name="search_results"),
    path("search/recent/", recent_searches_view, name="recent_searches"),
    path("search/suggestions/", search_suggestions_view, name="search_suggestions"),
]
