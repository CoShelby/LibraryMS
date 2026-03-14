import os

from django import forms
from django.db.models import Q

from books.models import Author, Book, BookCopy, Category, Publisher
from digital_library.models import DigitalLibrary


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _validate_image_file(file_obj, field_label):
    if not file_obj:
        return
    extension = os.path.splitext((file_obj.name or "").lower())[1]
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise forms.ValidationError(f"{field_label} يجب أن تكون صورة بامتداد: JPG/JPEG/PNG/WEBP")

    content_type = getattr(file_obj, "content_type", "") or ""
    if content_type and not content_type.startswith("image/"):
        raise forms.ValidationError(f"{field_label} ليست ملف صورة صالح.")


class BookForm(forms.ModelForm):
    author_names = forms.CharField(required=True, label="المؤلف/المؤلفون")
    category_name = forms.CharField(required=True, label="الفئة")
    publisher_name = forms.CharField(required=True, label="الناشر")
    copies_count = forms.IntegerField(required=False, min_value=0, initial=1, label="عدد النسخ")

    class Meta:
        model = Book
        fields = [
            "title",
            "dewey_decimal_number",
            "publication_year",
            "edition",
            "language",
            "pages",
            "description",
            "cover_image",
        ]
        labels = {
            "title": "عنوان الكتاب",
            "dewey_decimal_number": "رقم ديوي",
            "publication_year": "سنة النشر",
            "edition": "الطبعة",
            "language": "لغة الكتاب",
            "pages": "عدد الصفحات",
            "description": "الوصف",
            "cover_image": "صورة الغلاف",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "input-field", "placeholder": "عنوان الكتاب"}),
            "dewey_decimal_number": forms.TextInput(attrs={"class": "input-field", "dir": "ltr", "placeholder": "مثال: 005.133"}),
            "publication_year": forms.NumberInput(attrs={"class": "input-field", "placeholder": "مثال: 2024"}),
            "edition": forms.TextInput(attrs={"class": "input-field", "placeholder": "اختياري"}),
            "language": forms.Select(attrs={"class": "input-field"}),
            "pages": forms.NumberInput(attrs={"class": "input-field", "placeholder": "اختياري"}),
            "description": forms.Textarea(attrs={"class": "input-field", "rows": 4, "placeholder": "وصف مختصر"}),
            "cover_image": forms.ClearableFileInput(attrs={"class": "input-field", "accept": "image/*"}),
        }

    @staticmethod
    def _split_names(raw_value):
        prepared = (raw_value or "").replace("،", ",")
        values = [name.strip() for name in prepared.split(",") if name.strip()]
        return list(dict.fromkeys(values))

    @staticmethod
    def _get_or_create_category(name):
        category = Category.objects.filter(Q(name__iexact=name) | Q(name_en__iexact=name)).first()
        if category:
            return category
        return Category.objects.create(name=name, name_en="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["author_names"].widget.attrs.update(
            {
                "class": "input-field",
                "placeholder": "اكتب الاسم، ويمكن إدخال أكثر من اسم بالفاصلة",
                "list": "authors-options",
            }
        )
        self.fields["category_name"].widget.attrs.update(
            {
                "class": "input-field",
                "placeholder": "اكتب اسم الفئة أو اختر من المقترحات",
                "list": "categories-options",
            }
        )
        self.fields["publisher_name"].widget.attrs.update(
            {
                "class": "input-field",
                "placeholder": "اكتب اسم الناشر أو اختر من المقترحات",
                "list": "publishers-options",
            }
        )
        self.fields["copies_count"].widget.attrs.update({"class": "input-field", "placeholder": "مثال: 1"})

        if self.instance and self.instance.pk:
            self.fields["author_names"].initial = "، ".join(self.instance.authors.values_list("name", flat=True))
            self.fields["category_name"].initial = self.instance.category.name if self.instance.category else ""
            self.fields["publisher_name"].initial = self.instance.publisher.name if self.instance.publisher else ""
            self.fields["copies_count"].initial = 0
            self.fields["copies_count"].label = "إضافة نسخ جديدة"

    def clean_author_names(self):
        values = self._split_names(self.cleaned_data.get("author_names"))
        if not values:
            raise forms.ValidationError("أدخل اسم مؤلف واحد على الأقل.")
        return "، ".join(values)

    def clean_category_name(self):
        value = (self.cleaned_data.get("category_name") or "").strip()
        if not value:
            raise forms.ValidationError("اسم الفئة مطلوب.")
        return value

    def clean_publisher_name(self):
        value = (self.cleaned_data.get("publisher_name") or "").strip()
        if not value:
            raise forms.ValidationError("اسم الناشر مطلوب.")
        return value

    def clean_cover_image(self):
        cover = self.cleaned_data.get("cover_image")
        _validate_image_file(cover, "صورة الغلاف")
        return cover

    def save(self, commit=True):
        book = super().save(commit=False)
        is_new = self.instance.pk is None

        category_name = self.cleaned_data["category_name"].strip()
        publisher_name = self.cleaned_data["publisher_name"].strip()
        author_names = self._split_names(self.cleaned_data.get("author_names"))

        book.category = self._get_or_create_category(category_name)
        publisher, _ = Publisher.objects.get_or_create(name=publisher_name)
        book.publisher = publisher

        if commit:
            book.save()
            author_objects = []
            for author_name in author_names:
                author, _ = Author.objects.get_or_create(name=author_name)
                author_objects.append(author)
            book.authors.set(author_objects)

            copies_to_add = self.cleaned_data.get("copies_count")
            if copies_to_add is None:
                copies_to_add = 1 if is_new else 0

            existing_numbers = []
            for value in book.bookcopy_set.values_list("copy_number", flat=True):
                if value and str(value).isdigit():
                    existing_numbers.append(int(value))
            next_number = (max(existing_numbers) if existing_numbers else 0) + 1

            for _ in range(copies_to_add):
                copy_number = str(next_number)
                BookCopy.objects.create(
                    book=book,
                    copy_number=copy_number,
                    barcode=f"{book.id}-{copy_number}",
                    status="new",
                )
                next_number += 1

        return book


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "name_en", "shelf_location"]
        labels = {
            "name": "اسم الفئة (عربي)",
            "name_en": "اسم الفئة (English)",
            "shelf_location": "موقع الرف",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": "مثال: الذكاء الاصطناعي"}),
            "name_en": forms.TextInput(attrs={"class": "input-field", "placeholder": "Artificial Intelligence"}),
            "shelf_location": forms.TextInput(attrs={"class": "input-field", "placeholder": "مثال: A-12"}),
        }


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ["name"]
        labels = {"name": "اسم المؤلف"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": "اسم المؤلف"}),
        }


class PublisherForm(forms.ModelForm):
    class Meta:
        model = Publisher
        fields = ["name", "city", "country"]
        labels = {
            "name": "اسم الناشر",
            "city": "المدينة",
            "country": "الدولة",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field", "placeholder": "اسم الناشر"}),
            "city": forms.TextInput(attrs={"class": "input-field", "placeholder": "اختياري"}),
            "country": forms.TextInput(attrs={"class": "input-field", "placeholder": "اختياري"}),
        }


class BookCopyForm(forms.ModelForm):
    class Meta:
        model = BookCopy
        fields = ["copy_number", "barcode", "status"]
        labels = {
            "copy_number": "رقم النسخة",
            "barcode": "رمز QR",
            "status": "حالة النسخة",
        }
        widgets = {
            "copy_number": forms.TextInput(attrs={"class": "input-field", "placeholder": "اتركه فارغًا للترقيم التلقائي"}),
            "barcode": forms.TextInput(attrs={"class": "input-field", "placeholder": "اتركه فارغًا للتوليد التلقائي (bookId-copy)"}),
            "status": forms.Select(attrs={"class": "input-field"}),
        }


class DigitalLibraryForm(forms.ModelForm):
    create_new_book = forms.BooleanField(required=False, label="إضافة كتاب جديد مع الملف")
    new_title = forms.CharField(required=False, label="عنوان الكتاب")
    new_author_names = forms.CharField(required=False, label="المؤلف/المؤلفون")
    new_category_name = forms.CharField(required=False, label="الفئة")
    new_publisher_name = forms.CharField(required=False, label="الناشر")
    new_dewey_decimal_number = forms.CharField(required=False, label="رقم ديوي")
    new_publication_year = forms.IntegerField(required=False, label="سنة النشر")
    new_language = forms.ChoiceField(required=False, choices=Book.LANGUAGE_CHOICES, label="لغة الكتاب")
    new_pages = forms.IntegerField(required=False, min_value=1, label="عدد الصفحات")
    new_description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="الوصف")
    new_cover_image = forms.ImageField(required=False, label="صورة الغلاف")

    class Meta:
        model = DigitalLibrary
        fields = ["book", "pdf_file"]
        labels = {
            "book": "اختيار كتاب ورقي موجود",
            "pdf_file": "ملف PDF",
        }
        widgets = {
            "book": forms.Select(attrs={"class": "input-field"}),
            "pdf_file": forms.ClearableFileInput(attrs={"class": "input-field", "accept": "application/pdf"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name in [
            "new_title",
            "new_author_names",
            "new_category_name",
            "new_publisher_name",
            "new_dewey_decimal_number",
            "new_publication_year",
            "new_language",
            "new_pages",
            "new_description",
            "new_cover_image",
        ]:
            self.fields[name].widget.attrs.update({"class": "input-field"})

        self.fields["new_title"].widget.attrs.update({"placeholder": "يمكن تركه فارغًا ليؤخذ من اسم الملف"})
        self.fields["create_new_book"].widget.attrs.update({"class": "h-4 w-4"})
        self.fields["new_author_names"].widget.attrs.update({"list": "authors-options"})
        self.fields["new_category_name"].widget.attrs.update({"list": "categories-options"})
        self.fields["new_publisher_name"].widget.attrs.update({"list": "publishers-options"})
        self.fields["new_language"].initial = "arabic"

        if self.instance and self.instance.pk:
            self.fields["book"].queryset = Book.objects.filter(
                Q(digitallibrary__isnull=True) | Q(pk=self.instance.book_id)
            )
        else:
            self.fields["book"].queryset = Book.objects.filter(digitallibrary__isnull=True)

        self.fields["book"].required = False

    def clean_pdf_file(self):
        pdf_file = self.cleaned_data.get("pdf_file")
        if not pdf_file:
            return pdf_file

        extension = os.path.splitext((pdf_file.name or "").lower())[1]
        if extension != ".pdf":
            raise forms.ValidationError("ملف الكتاب الرقمي يجب أن يكون PDF.")

        content_type = getattr(pdf_file, "content_type", "") or ""
        if content_type and "pdf" not in content_type.lower():
            raise forms.ValidationError("نوع الملف غير صالح. يرجى رفع ملف PDF.")

        return pdf_file

    def clean_new_cover_image(self):
        cover = self.cleaned_data.get("new_cover_image")
        _validate_image_file(cover, "صورة الغلاف")
        return cover

    def clean(self):
        cleaned_data = super().clean()
        create_new = cleaned_data.get("create_new_book")

        if create_new:
            required_new_fields = [
                "new_author_names",
                "new_category_name",
                "new_publisher_name",
                "new_dewey_decimal_number",
            ]
            for field_name in required_new_fields:
                value = cleaned_data.get(field_name)
                if isinstance(value, str):
                    value = value.strip()
                if not value:
                    self.add_error(field_name, "هذا الحقل مطلوب عند إنشاء كتاب جديد.")
        elif not cleaned_data.get("book"):
            self.add_error("book", "اختر كتابًا موجودًا أو فعّل إنشاء كتاب جديد.")

        return cleaned_data
