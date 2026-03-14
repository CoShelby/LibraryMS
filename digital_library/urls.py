from django.urls import path

from . import views

urlpatterns = [
    path("", views.digital_books_list, name="digital_list"),
    path("read/<int:book_id>/", views.read_digital_book, name="read_digital_book"),
    path("download/<int:book_id>/", views.download_digital_book, name="download_digital_book"),
]
