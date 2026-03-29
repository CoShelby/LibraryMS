from django.urls import path

from . import views

urlpatterns = [
    path("", views.member_list, name="member_list"),
    path("print-cards/", views.print_member_cards, name="print_member_cards"),
    path("add/", views.add_member, name="add_member"),
    path("<int:member_id>/edit/", views.edit_member, name="edit_member"),
    path("<int:member_id>/delete/", views.delete_member, name="delete_member"),
]
