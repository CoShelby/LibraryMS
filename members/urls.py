from django.urls import path

from . import views

urlpatterns = [
    path("", views.member_list, name="member_list"),
    path("add/", views.add_member, name="add_member"),
    path("<int:member_id>/edit/", views.edit_member, name="edit_member"),
]
