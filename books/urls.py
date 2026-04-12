from django.urls import path

from .views import book_detail_view, book_list_view, most_viewed_books_view

urlpatterns = [
    path('list/', book_list_view, name="book_list"),
    path('most-viewed/', most_viewed_books_view, name="most_viewed_books"),
    path("<int:book_id>/", book_detail_view, name="book_detail"),
]
