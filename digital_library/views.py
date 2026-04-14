from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from books.forms import BookSearchForm
from books.selectors import search_books

from .models import DigitalLibrary

FILTER_TRIGGER_FIELDS = (
    "query",
    "category",
    "author",
    "publisher",
    "min_pages",
    "max_pages",
    "year",
    "language",
)


def _has_active_filters(request):
    for field in FILTER_TRIGGER_FIELDS:
        value = request.GET.get(field)
        if value and str(value).strip():
            return True
    return False


def _digital_filter_form(request):
    form = BookSearchForm(request.GET or None, initial={"search_scope": "digital"})
    form.fields["search_scope"].initial = "digital"
    return form


def _ordered_digital_books(books):
    if hasattr(books, "order_by"):
        books = books.order_by("title")
    book_list = list(books)
    if not book_list:
        return []

    entries = DigitalLibrary.objects.select_related("book", "book__category").filter(
        book_id__in=[book.id for book in book_list]
    )
    by_book_id = {entry.book_id: entry for entry in entries}
    return [by_book_id[book.id] for book in book_list if book.id in by_book_id]


def digital_books_list(request):
    form = _digital_filter_form(request)

    if form.is_valid():
        books = search_books(
            query=form.cleaned_data.get("query"),
            category=form.cleaned_data.get("category"),
            author=form.cleaned_data.get("author"),
            publisher=form.cleaned_data.get("publisher"),
            min_pages=form.cleaned_data.get("min_pages"),
            max_pages=form.cleaned_data.get("max_pages"),
            year=form.cleaned_data.get("year"),
            language=form.cleaned_data.get("language"),
            search_scope="digital",
        )
        digital_books = _ordered_digital_books(books)
    else:
        digital_books = list(DigitalLibrary.objects.select_related("book", "book__category").order_by("book__title"))

    return render(
        request,
        "digital/list.html",
        {
            "digital_books": digital_books,
            "filter_form": form,
            "filters_active": _has_active_filters(request),
            "fixed_search_scope": "digital",
        },
    )


def read_digital_book(request, book_id):
    digital_book = get_object_or_404(DigitalLibrary, book_id=book_id)
    return render(request, "digital/read.html", {"digital_book": digital_book})


def download_digital_book(request, book_id):
    digital_book = get_object_or_404(DigitalLibrary, book_id=book_id)
    if not digital_book.pdf_file:
        raise Http404("PDF file not found")

    file_handle = digital_book.pdf_file.open("rb")
    response = FileResponse(file_handle, as_attachment=True, filename=digital_book.pdf_file.name.split("/")[-1])
    return response