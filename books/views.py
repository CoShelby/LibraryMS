from django.db.models import Count, ExpressionWrapper, F, IntegerField, Q
from django.shortcuts import get_object_or_404, render

from .models import Book
from .selectors import get_similar_books


def _books_queryset(ordering=("title",), physical_only=True):
    qs = (
        Book.objects.select_related("category", "publisher")
        .prefetch_related("authors")
        .annotate(
            total_copies_count=Count("bookcopy", distinct=True),
            usable_copies_count=Count("bookcopy", filter=Q(bookcopy__status="new"), distinct=True),
            active_borrowings_count=Count(
                "bookcopy__borrowing",
                filter=Q(bookcopy__borrowing__return_date__isnull=True),
                distinct=True,
            ),
            approved_reservations_count=Count("reservation", filter=Q(reservation__status="approved"), distinct=True),
        )
        .annotate(
            available_copies_count=ExpressionWrapper(
                F("usable_copies_count") - F("active_borrowings_count") - F("approved_reservations_count"),
                output_field=IntegerField(),
            )
        )
    )
    if physical_only:
        qs = qs.filter(total_copies_count__gt=0)
    return qs.order_by(*ordering)


def book_list_view(request):
    books = _books_queryset(ordering=("title",), physical_only=True)
    return render(
        request,
        "books/book_list.html",
        {
            "books": books,
            "page_title": "دليل الكتب الورقية",
            "page_description": "استعراض جميع الكتب الورقية المتاحة داخل المكتبة.",
        },
    )


def most_viewed_books_view(request):
    books = _books_queryset(ordering=("-view_count", "title"), physical_only=False)
    return render(
        request,
        "books/book_list.html",
        {
            "books": books,
            "page_title": "الأكثر مشاهدة",
            "page_description": "الكتب الأعلى مشاهدة مرتبة من الأكثر إلى الأقل.",
            "show_view_count": True,
        },
    )


def book_detail_view(request, book_id):
    book = get_object_or_404(
        Book.objects.select_related("category", "publisher").prefetch_related("authors"),
        id=book_id,
    )

    book.view_count += 1
    book.save(update_fields=["view_count"])

    total_copies_count = book.bookcopy_set.count()
    usable_copies_count = book.bookcopy_set.filter(status="new").count()
    active_borrowings_count = book.bookcopy_set.filter(
        borrowing__isnull=False,
        borrowing__return_date__isnull=True,
    ).distinct().count()
    approved_reservations_count = book.reservation_set.filter(status="approved").count()
    available_copies_count = max(usable_copies_count - active_borrowings_count - approved_reservations_count, 0)

    has_physical_copies = total_copies_count > 0
    digital_copy = getattr(book, "digitallibrary", None)
    similar_books = get_similar_books(book, limit=6)

    context = {
        "book": book,
        "total_copies_count": total_copies_count,
        "available_copies_count": available_copies_count,
        "is_available": available_copies_count > 0,
        "has_physical_copies": has_physical_copies,
        "digital_copy": digital_copy,
        "similar_books": similar_books,
    }
    return render(request, "books/book_detail.html", context)
