from django.http import JsonResponse
from django.shortcuts import render

from books.forms import BookSearchForm
from books.services import (
    get_homepage_data,
    record_categories_from_results,
    record_category_search,
    search_books_service,
    search_suggestions_service,
)
from emails.member_messages import sync_automatic_member_messages

SEARCH_TRIGGER_FIELDS = [
    "query",
    "category",
    "author",
    "publisher",
    "min_pages",
    "max_pages",
    "year",
    "language",
    "search_scope",
]


def _has_active_search(request):
    for field in SEARCH_TRIGGER_FIELDS:
        value = request.GET.get(field)
        if value and str(value).strip() and not (field == "search_scope" and value == "all"):
            return True
    return False


def _store_recent_search(request, query):
    cleaned = (query or "").strip()
    if not cleaned:
        return

    recent = request.session.get("recent_searches", [])
    if cleaned in recent:
        recent.remove(cleaned)
    recent.insert(0, cleaned)
    request.session["recent_searches"] = recent[:10]


def home_view(request):
    sync_automatic_member_messages()
    data = get_homepage_data()
    context = {
        "popular_books": data["popular_books"],
        "recent_books": data["recent_books"],
        "popular_categories": data["popular_categories"],
    }
    return render(request, "public/home.html", context)


def search_results_view(request):
    form = BookSearchForm(request.GET or None)
    books = []
    has_active_search = _has_active_search(request)
    recent_searches = request.session.get("recent_searches", [])

    if form.is_valid() and has_active_search:
        books = search_books_service(
            query=form.cleaned_data.get("query"),
            category=form.cleaned_data.get("category"),
            author=form.cleaned_data.get("author"),
            publisher=form.cleaned_data.get("publisher"),
            min_pages=form.cleaned_data.get("min_pages"),
            max_pages=form.cleaned_data.get("max_pages"),
            year=form.cleaned_data.get("year"),
            language=form.cleaned_data.get("language"),
            search_scope=form.cleaned_data.get("search_scope") or "all",
        )
        query_value = form.cleaned_data.get("query")
        selected_category = form.cleaned_data.get("category")

        _store_recent_search(request, query_value)
        recent_searches = request.session.get("recent_searches", [])

        if selected_category:
            record_category_search(selected_category, weight=3)
        elif query_value:
            record_categories_from_results(books, max_items=20)

    return render(
        request,
        "public/search_results.html",
        {
            "form": form,
            "books": books,
            "has_active_search": has_active_search,
            "recent_searches": recent_searches,
        },
    )


def search_suggestions_view(request):
    query = (request.GET.get("q") or "").strip()
    suggestions = search_suggestions_service(query=query, limit=10) if query else []
    return JsonResponse({"results": suggestions})


def recent_searches_view(request):
    return JsonResponse({"results": request.session.get("recent_searches", [])})
