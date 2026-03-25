from .selectors import get_popular_books, get_popular_categories, get_recent_books, get_search_suggestions, search_books


def search_books_service(**kwargs):
    return search_books(**kwargs)


def search_suggestions_service(query, limit=8):
    return get_search_suggestions(query=query, limit=limit)


def get_homepage_data():
    return {
        "recent_books": get_recent_books(),
        "popular_books": get_popular_books(),
        "popular_categories": get_popular_categories(),
    }
