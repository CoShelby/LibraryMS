from django.db import models
from books.models import Book

class DigitalLibrary(models.Model):
    book = models.OneToOneField(Book, on_delete=models.CASCADE)
    pdf_file = models.FileField(upload_to='books/pdfs/', blank=True, null=True)

    def __str__(self):
        return self.book.title
