from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Value,
    When,
)

from digital_library.models import DigitalLibrary

from .models import Book, Category


def _base_books_queryset():
    books = (
        Book.objects.select_related("category", "publisher")
        .prefetch_related("authors")
        .annotate(
            has_digital=Exists(DigitalLibrary.objects.filter(book_id=OuterRef("pk"))),
            total_copies=Count("bookcopy", distinct=True),
            usable_copies=Count("bookcopy", filter=Q(bookcopy__status="new"), distinct=True),
            active_borrowings=Count(
                "bookcopy__borrowing",
                filter=Q(bookcopy__borrowing__return_date__isnull=True),
                distinct=True,
            ),
            approved_reservations=Count("reservation", filter=Q(reservation__status="approved"), distinct=True),
        )
        .annotate(
            available_copies_raw=ExpressionWrapper(
                F("usable_copies") - F("active_borrowings") - F("approved_reservations"),
                output_field=IntegerField(),
            )
        )
        .annotate(
            available_copies=Case(
                When(available_copies_raw__gt=0, then=F("available_copies_raw")),
                default=Value(0),
                output_field=IntegerField(),
            ),
            has_available_copies=Case(
                When(available_copies__gt=0, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
            has_physical_copy=Case(
                When(total_copies__gt=0, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
        )
    )
    return books


def search_books(
    query=None,
    category=None,
    author=None,
    publisher=None,
    min_pages=None,
    max_pages=None,
    year=None,
    language=None,
    search_scope="all",
):
    books = _base_books_queryset()

    if search_scope == "digital":
        books = books.filter(has_digital=True)
    elif search_scope == "physical":
        books = books.filter(has_physical_copy=True)

    if query:
        words = [word.strip() for word in query.split() if word.strip()]
        for word in words:
            books = books.filter(
                Q(title__icontains=word)
                | Q(description__icontains=word)
                | Q(authors__name__icontains=word)
                | Q(category__name__icontains=word)
                | Q(category__name_en__icontains=word)
                | Q(publisher__name__icontains=word)
                | Q(dewey_decimal_number__icontains=word)
            )

        relevance = (
            Case(When(title__iexact=query, then=Value(120)), default=Value(0), output_field=IntegerField())
            + Case(When(title__icontains=query, then=Value(60)), default=Value(0), output_field=IntegerField())
            + Case(When(authors__name__icontains=query, then=Value(40)), default=Value(0), output_field=IntegerField())
            + Case(When(category__name__icontains=query, then=Value(30)), default=Value(0), output_field=IntegerField())
            + Case(When(category__name_en__icontains=query, then=Value(30)), default=Value(0), output_field=IntegerField())
            + Case(When(publisher__name__icontains=query, then=Value(20)), default=Value(0), output_field=IntegerField())
            + Case(When(dewey_decimal_number__icontains=query, then=Value(25)), default=Value(0), output_field=IntegerField())
            + Case(When(description__icontains=query, then=Value(10)), default=Value(0), output_field=IntegerField())
        )
        books = books.annotate(relevance=relevance)
    else:
        books = books.annotate(relevance=Value(0, output_field=IntegerField()))

    if category:
        books = books.filter(category=category)

    if author:
        books = books.filter(authors=author)

    if publisher:
        books = books.filter(publisher=publisher)

    if min_pages:
        books = books.filter(pages__gte=min_pages)

    if max_pages:
        books = books.filter(pages__lte=max_pages)

    if year:
        books = books.filter(publication_year=year)

    if language:
        books = books.filter(language=language)

    return books.distinct().order_by("-relevance", "-has_digital", "-view_count", "title")


def get_popular_books():
    return _base_books_queryset().order_by("-view_count", "title")[:8]


def get_recent_books():
    return _base_books_queryset().order_by("-created_at")[:8]


def get_popular_categories(limit=8):
    return Category.objects.annotate(book_count=Count("book")).order_by("-book_count", "name")[:limit]


def get_homepage_data():
    return {
        "popular_books": get_popular_books(),
        "recent_books": get_recent_books(),
        "popular_categories": get_popular_categories(),
    }
