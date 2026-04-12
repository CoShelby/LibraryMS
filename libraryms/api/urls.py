from rest_framework.routers import DefaultRouter
from django.urls import path

from .registry import API_MODELS
from .views import AUTO_VIEWSETS, most_viewed_books_endpoint, recent_searches_endpoint

router = DefaultRouter()
for model in API_MODELS:
    route_name = model._meta.model_name.replace('_', '-')
    router.register(route_name, AUTO_VIEWSETS[model], basename=route_name)

urlpatterns = [
    path("most-viewed-books/", most_viewed_books_endpoint, name="api-most-viewed-books"),
    path("recent-searches/", recent_searches_endpoint, name="api-recent-searches"),
] + router.urls
