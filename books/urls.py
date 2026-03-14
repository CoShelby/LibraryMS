from django.urls import path
from .views import book_detail_view, book_list_view

urlpatterns = [
    path('list/', book_list_view, name="book_list"),
    path("<int:book_id>/", book_detail_view, name="book_detail"),
]