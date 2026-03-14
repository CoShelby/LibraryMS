from .models import DigitalLibrary


def get_all_digital_books():
    return DigitalLibrary.objects.select_related("book").all()


def get_popular_digital_books(limit=10):
    return DigitalLibrary.objects.select_related("book").order_by("-book__view_count")[:limit]
