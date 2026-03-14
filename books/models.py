from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    category_id = models.CharField(max_length=50, unique=True, blank=True)
    name = models.CharField(max_length=200)  # Arabic name
    name_en = models.CharField(max_length=200, blank=True, default="")
    shelf_location = models.CharField(max_length=200, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.category_id:
            base = slugify(self.name_en or self.name).upper().replace("-", "_")[:40] or "CATEGORY"
            candidate = base
            counter = 1
            while Category.objects.filter(category_id=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}_{counter}"
                counter += 1
            self.category_id = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Author(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class Publisher(models.Model):
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name


class Book(models.Model):
    LANGUAGE_CHOICES = [
        ("arabic", "العربية"),
        ("english", "الإنجليزية"),
    ]

    dewey_decimal_number = models.CharField(max_length=100)
    title = models.CharField(max_length=300)
    authors = models.ManyToManyField(Author)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    publisher = models.ForeignKey(Publisher, on_delete=models.SET_NULL, null=True)
    publication_year = models.IntegerField(blank=True, null=True)
    edition = models.CharField(max_length=50, blank=True, null=True)
    volume = models.CharField(max_length=50, blank=True, null=True)
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default="arabic")
    pages = models.IntegerField(blank=True, null=True)
    cover_image = models.ImageField(upload_to="books/covers/", blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    view_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title


class BookCopy(models.Model):
    STATUS = [
        ("new", "جديد"),
        ("damaged", "تالف"),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    copy_number = models.CharField(max_length=50, blank=True, null=True)
    barcode = models.CharField(max_length=100, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="new")

    def _next_copy_number(self):
        existing = (
            BookCopy.objects.filter(book=self.book)
            .exclude(pk=self.pk)
            .values_list("copy_number", flat=True)
        )
        numeric = []
        for value in existing:
            if value and str(value).isdigit():
                numeric.append(int(value))
        return str((max(numeric) if numeric else 0) + 1)

    def save(self, *args, **kwargs):
        if self.book_id and not (self.copy_number or "").strip():
            self.copy_number = self._next_copy_number()

        if self.book_id and not (self.barcode or "").strip():
            self.barcode = f"{self.book_id}-{self.copy_number}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.book.title} - {self.barcode}"
