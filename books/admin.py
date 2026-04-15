from django.contrib import admin

from .models import Author, Book, BookCopy, Category, CategorySearchStat, Publisher


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "name_en", "category_id", "shelf_location")
    search_fields = ("name", "name_en", "category_id")


@admin.register(CategorySearchStat)
class CategorySearchStatAdmin(admin.ModelAdmin):
    list_display = ("category", "search_count", "updated_at")
    search_fields = ("category__name", "category__name_en")


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "country")
    search_fields = ("name",)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "isbn", "category", "publisher", "created_by", "publication_year", "language", "view_count")
    search_fields = ("title", "isbn", "dewey_decimal_number")
    list_filter = ("category", "publication_year", "language")


@admin.register(BookCopy)
class BookCopyAdmin(admin.ModelAdmin):
    list_display = ("book", "barcode", "copy_number", "status", "is_printed", "created_at")
    search_fields = ("barcode", "copy_number", "book__title")
    list_filter = ("status", "is_printed")


