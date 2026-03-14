from django.urls import path

from .views import (
    borrow_view,
    cancel_reservation_view,
    member_portal_view,
    renew_borrowing_view,
    reserve_view,
)

urlpatterns = [
    path("borrow/<int:book_id>/", borrow_view, name="borrow_book"),
    path("reserve/<int:book_id>/", reserve_view, name="reserve_book"),
    path("member/", member_portal_view, name="member_portal"),
    path("renew/<int:borrowing_id>/", renew_borrowing_view, name="renew_borrowing"),
    path("cancel-reservation/<int:reservation_id>/", cancel_reservation_view, name="cancel_reservation"),
]
