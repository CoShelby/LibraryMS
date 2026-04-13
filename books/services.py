import string
from collections import Counter

from django.db.models import F, Q

from .models import Book, CategorySearchStat
from .selectors import get_popular_books, get_popular_categories, get_recent_books, get_search_suggestions, search_books


def search_books_service(**kwargs):
    return search_books(**kwargs)


def search_suggestions_service(query, limit=8):
    return get_search_suggestions(query=query, limit=limit)


def get_homepage_data():
    return {
        "recent_books": get_recent_books(),
        "popular_books": get_popular_books(limit=5),
        "popular_categories": get_popular_categories(),
    }


def record_category_search(category, weight=1):
    if not category:
        return

    try:
        weight_value = int(weight)
    except (TypeError, ValueError):
        weight_value = 1
    weight_value = max(weight_value, 1)

    stat, created = CategorySearchStat.objects.get_or_create(category=category)
    if created:
        stat.search_count = weight_value
        stat.save(update_fields=["search_count", "updated_at"])
        return

    CategorySearchStat.objects.filter(pk=stat.pk).update(search_count=F("search_count") + weight_value)


def record_categories_from_results(books, max_items=20):
    if not books:
        return

    counts = Counter()
    for book in list(books)[:max_items]:
        category = getattr(book, "category", None)
        if category:
            counts[category] += 1

    for category, hit_count in counts.items():
        record_category_search(category, weight=hit_count)


def get_similar_books(book, limit=6):
    author_ids = [a.id for a in book.authors.all()]

    candidates = Book.objects.exclude(id=book.id).filter(
        Q(category=book.category)
        | Q(authors__in=author_ids)
        | Q(language=book.language)
    ).distinct().select_related("category").prefetch_related("authors")

    def extract_keywords(text):
        if not text:
            return set()
        clean = text.translate(str.maketrans('', '', string.punctuation)).lower()
        words = clean.split()
        stopwords = {'في', 'من', 'إلى', 'على', 'عن', 'التي', 'الذي', 'و', 'أو', 'لا', 'ما', 'مع', 'كتاب'}
        return set(w for w in words if len(w) > 2 and w not in stopwords)

    book_keywords = extract_keywords(book.title)

    scored_books = []
    category_id = book.category_id

    for candidate in candidates:
        score = 0
        if candidate.category_id == category_id:
            score += 5

        cand_author_ids = [a.id for a in candidate.authors.all()]
        if any(aid in author_ids for aid in cand_author_ids):
            score += 3

        if candidate.language == book.language:
            score += 1

        candidate_keywords = extract_keywords(candidate.title)
        overlap = book_keywords.intersection(candidate_keywords)
        score += len(overlap) * 2

        scored_books.append((score, candidate))

    scored_books.sort(key=lambda x: (-x[0], -x[1].view_count))
    return [item[1] for item in scored_books[:limit]]




