from .models import DigitalLibrary


def increase_view(digital_book):
    book = digital_book.book
    book.view_count += 1
    book.save(update_fields=["view_count"])


def get_all_digital_books():
    return DigitalLibrary.objects.select_related("book").all()
