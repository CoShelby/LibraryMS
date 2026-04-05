from django.db.models.signals import post_delete
from django.dispatch import receiver

from books.models import Book, BookCopy
from digital_library.models import DigitalLibrary

@receiver(post_delete, sender=BookCopy)
@receiver(post_delete, sender=DigitalLibrary)
def check_and_delete_empty_book(sender, instance, **kwargs):
    if not instance.book_id:
        return
    book = Book.objects.filter(id=instance.book_id).first()
    if not book:
        return
    
    has_physical = BookCopy.objects.filter(book=book).exists()
    has_digital = DigitalLibrary.objects.filter(book=book).exists()
    
    if not has_physical and not has_digital:
        book.delete()
