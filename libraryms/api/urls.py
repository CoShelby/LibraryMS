from django.urls import path
from rest_framework.routers import DefaultRouter

from .member_fines import (
    ExternalFinePaymentAPIView,
    FineStatusAPIView,
    MemberFullStatusAPIView,
    MemberSearchAPIView,
    MembersWithIssuesAPIView,
)
from .registry import API_MODELS
from .views import AUTO_VIEWSETS, most_viewed_books_endpoint, recent_searches_endpoint

router = DefaultRouter()
for model in API_MODELS:
    route_name = model._meta.model_name.replace("_", "-")
    router.register(route_name, AUTO_VIEWSETS[model], basename=route_name)

urlpatterns = [
    path("most-viewed-books/", most_viewed_books_endpoint, name="api-most-viewed-books"),
    path("recent-searches/", recent_searches_endpoint, name="api-recent-searches"),
    path("members/search/", MemberSearchAPIView.as_view(), name="api-member-search"),
    path("members/issues/", MembersWithIssuesAPIView.as_view(), name="api-members-with-issues"),
    path("members/<int:member_id>/status/", MemberFullStatusAPIView.as_view(), name="api-member-full-status"),
    path("fines/<int:fine_id>/status/", FineStatusAPIView.as_view(), name="api-fine-status"),
    path("fines/<int:fine_id>/payments/", ExternalFinePaymentAPIView.as_view(), name="api-fine-payment"),
] + router.urls
