from books.models import BookCopy

from .models import Borrowing, Reservation


def get_available_copy(book):
    active_copy_ids = Borrowing.objects.filter(book_copy__book=book, return_date__isnull=True).values_list(
        "book_copy_id", flat=True
    )
    return BookCopy.objects.filter(book=book, status="new").exclude(id__in=active_copy_ids).first()


def member_active_borrowings(member):
    return Borrowing.objects.filter(member=member, return_date__isnull=True)


def member_reservations(member):
    return Reservation.objects.filter(member=member, status__in=["pending", "approved"])


def is_book_reserved(book):
    return Reservation.objects.filter(book=book, status="approved").exists()
