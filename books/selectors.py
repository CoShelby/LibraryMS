import re
from collections import OrderedDict
from functools import lru_cache

from django.core.cache import cache
from django.db import models
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

from .models import Book, BookCopy, Category

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback only when dependency is unavailable
    fuzz = None

_ARABIC_VARIANTS = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
    }
)
_ARABIC_DIACRITICS_RE = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u0640]")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

_TEXT_FIELD_TYPES = (
    models.CharField,
    models.TextField,
    models.EmailField,
    models.SlugField,
    models.URLField,
    models.UUIDField,
)
_NUMERIC_FIELD_TYPES = (
    models.IntegerField,
    models.PositiveIntegerField,
    models.PositiveBigIntegerField,
    models.BigIntegerField,
    models.FloatField,
    models.DecimalField,
)
_DATE_FIELD_TYPES = (models.DateField, models.DateTimeField)
_FILE_FIELD_TYPES = (models.FileField, models.ImageField)


def normalize_search_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.translate(_ARABIC_VARIANTS)
    text = _ARABIC_DIACRITICS_RE.sub("", text)
    text = _NON_WORD_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def normalize_isbn(value):
    return re.sub(r"[^0-9xX]", "", str(value or "")).upper()



def _fuzzy_ratio(query, text):
    normalized_query = normalize_search_text(query)
    normalized_text = normalize_search_text(text)
    if not normalized_query or not normalized_text:
        return 0
    if normalized_query == normalized_text:
        return 100
    if fuzz is not None:
        return max(
            fuzz.WRatio(normalized_query, normalized_text),
            fuzz.token_set_ratio(normalized_query, normalized_text),
            fuzz.partial_ratio(normalized_query, normalized_text),
        )

    if normalized_query in normalized_text or normalized_text in normalized_query:
        return 90

    query_words = set(normalized_query.split())
    text_words = set(normalized_text.split())
    if not query_words or not text_words:
        return 0
    overlap = len(query_words & text_words)
    return int((overlap / max(len(query_words), len(text_words))) * 100)


@lru_cache(maxsize=1)
def _book_lookup_specs():
    specs = []
    direct_fields = []

    for field in Book._meta.get_fields():
        if not getattr(field, "concrete", False) and not field.many_to_many:
            continue
        if getattr(field, "auto_created", False) and not field.concrete:
            continue
        if field.name == "id":
            continue

        if isinstance(field, _TEXT_FIELD_TYPES):
            direct_fields.append((field.name, "text"))
        elif isinstance(field, _NUMERIC_FIELD_TYPES):
            direct_fields.append((field.name, "numeric"))
        elif isinstance(field, _DATE_FIELD_TYPES):
            direct_fields.append((field.name, "date"))
        elif isinstance(field, _FILE_FIELD_TYPES):
            direct_fields.append((field.name, "file"))

        if field.is_relation and (field.many_to_one or field.one_to_one or field.many_to_many):
            related_model = field.related_model
            if related_model is None:
                continue
            for related_field in related_model._meta.get_fields():
                if not getattr(related_field, "concrete", False):
                    continue
                if getattr(related_field, "auto_created", False):
                    continue
                if related_field.name == "id":
                    continue
                if isinstance(related_field, _TEXT_FIELD_TYPES):
                    specs.append((f"{field.name}__{related_field.name}", "text"))
                elif isinstance(related_field, _NUMERIC_FIELD_TYPES):
                    specs.append((f"{field.name}__{related_field.name}", "numeric"))
                elif isinstance(related_field, _DATE_FIELD_TYPES):
                    specs.append((f"{field.name}__{related_field.name}", "date"))
                elif isinstance(related_field, _FILE_FIELD_TYPES):
                    specs.append((f"{field.name}__{related_field.name}", "file"))

    specs.extend(direct_fields)
    return specs


def _append_lookup_clause(query_object, lookup, field_type, raw_term):
    term = str(raw_term or "").strip()
    if not term:
        return query_object

    if field_type in {"text", "file"}:
        return query_object | Q(**{f"{lookup}__icontains": term})

    if field_type == "numeric":
        normalized = term.replace(",", "")
        if re.fullmatch(r"-?\d+", normalized):
            return query_object | Q(**{lookup: int(normalized)})
        return query_object

    if field_type == "date":
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", term):
            return query_object | Q(**{f"{lookup}__date": term})
        if re.fullmatch(r"\d{4}", term):
            return query_object | Q(**{f"{lookup}__year": int(term)})
        return query_object

    return query_object


def build_books_lookup_query(query):
    terms = [term for term in normalize_search_text(query).split() if term]
    if not terms:
        return Q()

    specs = _book_lookup_specs()
    query_object = Q()
    for term in terms:
        term_query = Q()
        for lookup, field_type in specs:
            term_query = _append_lookup_clause(term_query, lookup, field_type, term)
        query_object &= term_query
    return query_object


def _related_values_for_book(book):
    values = []
    for field in Book._meta.get_fields():
        if getattr(field, "auto_created", False) and not field.concrete:
            continue

        if field.many_to_many:
            manager = getattr(book, field.name)
            for related_obj in manager.all():
                for related_field in related_obj._meta.concrete_fields:
                    if related_field.name == "id":
                        continue
                    value = getattr(related_obj, related_field.name, None)
                    if value not in (None, ""):
                        values.append((field.name, str(value)))
            continue

        if field.is_relation and (field.many_to_one or field.one_to_one):
            related_obj = getattr(book, field.name, None)
            if related_obj is None:
                continue
            for related_field in related_obj._meta.concrete_fields:
                if related_field.name == "id":
                    continue
                value = getattr(related_obj, related_field.name, None)
                if value not in (None, ""):
                    values.append((field.name, str(value)))
            continue

        if field.concrete and field.name != "id":
            value = getattr(book, field.name, None)
            if value not in (None, ""):
                values.append((field.name, str(value)))

    digital = getattr(book, "digitallibrary", None)
    if digital and getattr(digital, "pdf_file", None):
        values.append(("digital_file", str(digital.pdf_file)))
    return values


def _book_score(query, book):
    normalized_query = normalize_search_text(query)
    title = normalize_search_text(book.title)
    exact_title = title == normalized_query
    partial_title = normalized_query in title if normalized_query and title else False

    best_score = 0
    direct_match = False
    for _, value in _related_values_for_book(book):
        normalized_value = normalize_search_text(value)
        if not normalized_value:
            continue
        if normalized_query in normalized_value:
            direct_match = True
        best_score = max(best_score, _fuzzy_ratio(normalized_query, normalized_value))

    title_score = _fuzzy_ratio(normalized_query, book.title)
    best_score = max(best_score, title_score)

    return {
        "exact_title": exact_title,
        "partial_title": partial_title,
        "direct_match": direct_match,
        "best_score": best_score,
        "title_score": title_score,
    }


def _base_books_queryset():
    return (
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

    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return books.distinct().order_by("-view_count", "title")

    lookup_query = build_books_lookup_query(normalized_query)
    candidates_queryset = books.filter(lookup_query).distinct() if lookup_query else books.distinct()
    candidates = list(candidates_queryset[:600])

    if not candidates:
        candidates = list(books.distinct().order_by("-view_count", "title")[:300])

    ranked = []
    for book in candidates:
        score = _book_score(normalized_query, book)
        if not (score["direct_match"] or score["best_score"] >= 80):
            continue
        ranked.append(
            (
                1 if score["exact_title"] else 0,
                1 if score["partial_title"] else 0,
                score["title_score"],
                score["best_score"],
                book.view_count,
                book,
            )
        )

    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], -item[4], item[5].title))
    if ranked:
        return [item[-1] for item in ranked]

    return list(candidates_queryset.order_by("-view_count", "title")[:100])


def get_search_suggestions(query, limit=8):
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return []

    cache_key = f"search:suggest:v2:{normalized_query}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    suggestions = OrderedDict()
    books = list(
        Book.objects.select_related("category", "publisher")
        .prefetch_related("authors")
        .filter(build_books_lookup_query(normalized_query))
        .distinct()
        .order_by("-view_count", "title")[:60]
    )

    def add_suggestion(value, kind, meta=""):
        cleaned = str(value or "").strip()
        if not cleaned:
            return
        score = _fuzzy_ratio(normalized_query, cleaned)
        if normalized_query not in normalize_search_text(cleaned) and score < 80:
            return
        key = f"{kind}:{cleaned.lower()}"
        current = suggestions.get(key)
        payload = {
            "value": cleaned,
            "label": cleaned,
            "kind": kind,
            "meta": meta,
            "score": score,
        }
        if current is None or payload["score"] > current["score"]:
            suggestions[key] = payload

    for book in books:
        authors = "، ".join(book.authors.values_list("name", flat=True))
        category_name = book.category.name if book.category else ""
        publisher_name = book.publisher.name if book.publisher else ""
        add_suggestion(book.title, "title", category_name or authors)
        add_suggestion(book.isbn, "isbn", book.title)
        add_suggestion(book.dewey_decimal_number, "dewey", book.title)
        add_suggestion(category_name, "category", book.title)
        add_suggestion(publisher_name, "publisher", book.title)
        for author_name in book.authors.values_list("name", flat=True):
            add_suggestion(author_name, "author", book.title)

    sorted_items = sorted(
        suggestions.values(),
        key=lambda item: (-item["score"], item["kind"], item["label"]),
    )[:limit]
    result = [{key: value for key, value in item.items() if key != "score"} for item in sorted_items]
    cache.set(cache_key, result, 300)
    return result


def get_popular_books(limit=20):
    return _base_books_queryset().order_by("-view_count", "title")[:limit]


def get_recent_books(limit=20):
    return _base_books_queryset().order_by("-created_at")[:limit]


def get_popular_categories(limit=5):
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
        "popular_books": get_popular_books(limit=5),
        "recent_books": get_recent_books(),
        "popular_categories": get_popular_categories(),
    }


def get_similar_books(book, limit=6):
    candidates = (
        Book.objects.exclude(id=book.id)
        .filter(
            Q(category=book.category)
            | Q(authors__in=book.authors.all())
            | Q(publisher=book.publisher)
        )
        .distinct()
        .select_related("category", "publisher")
        .prefetch_related("authors")
    )

    ranked = []
    for candidate in candidates:
        score = 0
        if candidate.category_id == book.category_id:
            score += 20
        if candidate.publisher_id == book.publisher_id and candidate.publisher_id:
            score += 10
        for author in candidate.authors.all():
            if book.authors.filter(id=author.id).exists():
                score += 15
        score += _fuzzy_ratio(book.title, candidate.title)
        ranked.append((score, candidate.view_count, candidate))

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2].title))
    return [item[2] for item in ranked[:limit]]


def record_category_search(category, weight=1):
    if not category:
        return

    try:
        weight_value = max(int(weight), 1)
    except (TypeError, ValueError):
        weight_value = 1

    from .models import CategorySearchStat

    stat, created = CategorySearchStat.objects.get_or_create(category=category)
    if created:
        stat.search_count = weight_value
    else:
        stat.search_count += weight_value
    stat.save(update_fields=["search_count", "updated_at"])


def record_categories_from_results(books, max_items=20):
    counts = OrderedDict()
    for book in list(books)[:max_items]:
        category = getattr(book, "category", None)
        if not category:
            continue
        counts[category.pk] = counts.get(category.pk, {"category": category, "count": 0})
        counts[category.pk]["count"] += 1

    for item in counts.values():
        record_category_search(item["category"], weight=item["count"])


def find_duplicate_book_conflict(*, title, isbn=""):
    cleaned_isbn = normalize_isbn(isbn)
    if cleaned_isbn:
        for candidate in (
            Book.objects.select_related("category", "publisher")
            .prefetch_related("authors")
            .exclude(isbn="")[:500]
        ):
            if normalize_isbn(candidate.isbn) == cleaned_isbn:
                return {
                    "type": "exact",
                    "book": candidate,
                    "score": 100,
                }

    normalized_title = normalize_search_text(title)
    if not normalized_title:
        return {"type": "none", "book": None, "score": 0}

    candidates = (
        Book.objects.select_related("category", "publisher")
        .prefetch_related("authors")
        .filter(title__isnull=False)
        .exclude(title="")[:250]
    )

    best_book = None
    best_score = 0
    for candidate in candidates:
        score = _fuzzy_ratio(normalized_title, candidate.title)
        if score > best_score:
            best_score = score
            best_book = candidate

    if best_book and best_score >= 80:
        return {
            "type": "similar",
            "book": best_book,
            "score": best_score,
        }

    return {"type": "none", "book": None, "score": best_score}


def add_copies_to_book(book, copies_count=1):
    try:
        copies_total = max(int(copies_count or 1), 1)
    except (TypeError, ValueError):
        copies_total = 1

    created_copies = []
    for _ in range(copies_total):
        created_copies.append(BookCopy.objects.create(book=book, status="new"))
    if created_copies:
        from dashboard.notifications import notify_reserved_book_available

        notify_reserved_book_available(book)
    return created_copies

