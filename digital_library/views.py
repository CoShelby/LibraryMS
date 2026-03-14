from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from .models import DigitalLibrary


def digital_books_list(request):
    digital_books = DigitalLibrary.objects.select_related("book")
    return render(request, "digital/list.html", {"digital_books": digital_books})


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
