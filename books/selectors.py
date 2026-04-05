import re

from django.core.cache import cache
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
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from digital_library.models import DigitalLibrary

from .models import Book, Category

_ARABIC_VARIANTS = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "?": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
    }
)
_ARABIC_DIACRITICS_RE = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u0640]")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _normalize_search_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.translate(_ARABIC_VARIANTS)
    text = _ARABIC_DIACRITICS_RE.sub("", text)
    text = _NON_WORD_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def _levenshtein_distance(first, second):
    if first == second:
        return 0
    if not first:
        return len(second)
    if not second:
        return len(first)

    if len(first) > len(second):
        first, second = second, first

    previous_row = list(range(len(first) + 1))
    for index_second, char_second in enumerate(second, start=1):
        current_row = [index_second]
        for index_first, char_first in enumerate(first, start=1):
            insertions = previous_row[index_first] + 1
            deletions = current_row[index_first - 1] + 1
            substitutions = previous_row[index_first - 1] + (char_first != char_second)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _lcs_length(first, second):
    if not first or not second:
        return 0

    rows = len(first) + 1
    cols = len(second) + 1
    table = [[0] * cols for _ in range(rows)]

    for i in range(1, rows):
        for j in range(1, cols):
            if first[i - 1] == second[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
            else:
                table[i][j] = max(table[i - 1][j], table[i][j - 1])
    return table[-1][-1]


def _longest_common_substring_length(first, second):
    if not first or not second:
        return 0

    rows = len(first) + 1
    cols = len(second) + 1
    table = [[0] * cols for _ in range(rows)]
    best = 0

    for i in range(1, rows):
        for j in range(1, cols):
            if first[i - 1] == second[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
                best = max(best, table[i][j])
    return best


def _text_similarity_score(query, text):
    query_text = _normalize_search_text(query)
    target_text = _normalize_search_text(text)

    if not query_text or not target_text:
        return 0.0

    if query_text == target_text:
        return 1.0

    max_length = max(len(query_text), len(target_text))
    levenshtein_ratio = 1 - (_levenshtein_distance(query_text, target_text) / max_length)
    lcs_ratio = _lcs_length(query_text, target_text) / len(query_text)
    lcss_ratio = _longest_common_substring_length(query_text, target_text) / len(query_text)

    partial_match = 1.0 if query_text in target_text else 0.0
    prefix_match = 1.0 if any(word.startswith(query_text) for word in target_text.split()) else 0.0

    score = (
        (levenshtein_ratio * 0.4)
        + (lcs_ratio * 0.25)
        + (lcss_ratio * 0.2)
        + (partial_match * 0.1)
        + (prefix_match * 0.05)
    )

    return max(score, 0.0)


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
                F("usable_copies") - F("active_borrowings"),
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


def _apply_common_filters(books, category=None, author=None, publisher=None, min_pages=None, max_pages=None, year=None, language=None):
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

    return books


def _book_similarity(query, book):
    title = _normalize_search_text(book.title)
    author_names = _normalize_search_text(" ".join(author.name for author in book.authors.all()))
    category_name = _normalize_search_text((book.category.name if book.category else "") + " " + (book.category.name_en if book.category else ""))
    publisher_name = _normalize_search_text(book.publisher.name if book.publisher else "")
    dewey = _normalize_search_text(book.dewey_decimal_number)
    description = _normalize_search_text(book.description)

    edition = _normalize_search_text(book.edition)
    language_display = _normalize_search_text(dict(Book.LANGUAGE_CHOICES).get(book.language, ""))
    year = _normalize_search_text(str(book.publication_year) if book.publication_year else "")
    pages = _normalize_search_text(str(book.pages) if book.pages else "")

    title_score = _text_similarity_score(query, title)
    author_score = _text_similarity_score(query, author_names)
    category_score = _text_similarity_score(query, category_name)
    publisher_score = _text_similarity_score(query, publisher_name)
    dewey_score = _text_similarity_score(query, dewey)
    description_score = _text_similarity_score(query, description)
    edition_score = _text_similarity_score(query, edition)
    language_score = _text_similarity_score(query, language_display)
    year_score = _text_similarity_score(query, year)
    pages_score = _text_similarity_score(query, pages)

    weighted_score = (
        (title_score * 0.42)
        + (author_score * 0.15)
        + (category_score * 0.08)
        + (publisher_score * 0.08)
        + (edition_score * 0.06)
        + (year_score * 0.06)
        + (language_score * 0.05)
        + (dewey_score * 0.04)
        + (pages_score * 0.03)
        + (description_score * 0.03)
    )

    query_normalized = _normalize_search_text(query)
    partial_in_title = query_normalized in title and title != query_normalized
    exact_in_title = title == query_normalized

    return {
        "weighted_score": weighted_score,
        "partial_in_title": partial_in_title,
        "exact_in_title": exact_in_title,
    }


def _rank_books_by_similarity(query, books):
    scored_books = []

    for book in books:
        similarity = _book_similarity(query, book)
        popularity_boost = min(book.view_count / 1000, 0.25)
        final_score = similarity["weighted_score"] + popularity_boost

        if final_score < 0.12:
            continue

        scored_books.append(
            (
                1 if similarity["partial_in_title"] else 0,
                final_score,
                1 if similarity["exact_in_title"] else 0,
                book.view_count,
                book,
            )
        )

    scored_books.sort(
        key=lambda row: (
            -row[0],  # partial matching first as requested
            -row[1],  # global similarity score
            -row[2],  # exact title match
            -row[3],  # popularity fallback
            row[4].title,
        )
    )

    return [item[4] for item in scored_books]


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

    books = _apply_common_filters(
        books,
        category=category,
        author=author,
        publisher=publisher,
        min_pages=min_pages,
        max_pages=max_pages,
        year=year,
        language=language,
    )

    query_text = _normalize_search_text(query)
    if not query_text:
        return books.distinct().order_by("-has_digital", "-view_count", "title")

    # خطوة أولى: تضييق النتائج بفلترة سريعة من قاعدة البيانات قبل حساب التشابه المتقدم.
    terms = [term for term in query_text.split() if term]
    lookup_query = Q()
    for term in terms:
        lookup_query |= (
            Q(title__icontains=term)
            | Q(description__icontains=term)
            | Q(authors__name__icontains=term)
            | Q(category__name__icontains=term)
            | Q(category__name_en__icontains=term)
            | Q(publisher__name__icontains=term)
            | Q(dewey_decimal_number__icontains=term)
        )

    candidates_queryset = books.filter(lookup_query).distinct() if lookup_query else books.distinct()
    candidates = list(candidates_queryset[:600])

    if not candidates:
        candidates = list(books.distinct().order_by("-view_count", "title")[:300])

    ranked = _rank_books_by_similarity(query_text, candidates)

    if ranked:
        return ranked

    return list(candidates_queryset.order_by("-view_count", "title")[:100])


def get_search_suggestions(query, limit=8):
    query_text = _normalize_search_text(query)
    if len(query_text) < 1:
        return []

    cache_key = f"search:suggest:{query_text}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    words = [item for item in query_text.split() if item]
    lookup = Q()
    for word in words:
        lookup |= Q(title__icontains=word)

    queryset = Book.objects.select_related("category").only("id", "title", "view_count", "category__name")
    if lookup:
        queryset = queryset.filter(lookup)

    candidates = list(queryset.distinct().order_by("-view_count", "title")[:120])

    ranked = []
    for book in candidates:
        score = _text_similarity_score(query_text, book.title)
        if score < 0.1:
            continue
        ranked.append((score, book.view_count, book))

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2].title))

    suggestions = [
        {
            "id": item[2].id,
            "title": item[2].title,
            "category": item[2].category.name if item[2].category else "-",
        }
        for item in ranked[:limit]
    ]

    cache.set(cache_key, suggestions, 300)
    return suggestions


def get_popular_books():
    return _base_books_queryset().order_by("-view_count", "title")[:8]


def get_recent_books():
    return _base_books_queryset().order_by("-created_at")[:8]


def get_popular_categories(limit=8):
    return (
        Category.objects.annotate(
            book_count=Count("book", distinct=True),
            view_score=Coalesce(Sum("book__view_count"), Value(0), output_field=IntegerField()),
            search_score=Coalesce(F("search_stat__search_count"), Value(0), output_field=IntegerField()),
        )
        .annotate(
            popularity_score=ExpressionWrapper(
                (F("search_score") * Value(4)) + F("view_score"),
                output_field=IntegerField(),
            )
        )
        .filter(popularity_score__gt=0)
        .order_by("-popularity_score", "-search_score", "-view_score", "-book_count", "name")[:limit]
    )


def get_homepage_data():
    return {
        "popular_books": get_popular_books(),
        "recent_books": get_recent_books(),
        "popular_categories": get_popular_categories(),
    }




