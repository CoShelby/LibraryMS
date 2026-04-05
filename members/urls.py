from django.urls import path

from . import views

urlpatterns = [
    path("", views.member_list, name="member_list"),
    path("add/", views.add_member, name="add_member"),
    path("<int:member_id>/edit/", views.edit_member, name="edit_member"),
    path("<int:member_id>/delete/", views.delete_member, name="delete_member"),
    path("print-cards/select/", views.print_cards_select, name="print_cards_select"),
    path("print-cards/", views.print_cards, name="print_cards"),
]

