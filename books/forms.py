from django import forms

from .models import Author, Category, Publisher


class BookSearchForm(forms.Form):
    SEARCH_SCOPE = [
        ("all", "الكل"),
        ("physical", "كتب ورقية فقط"),
        ("digital", "محتوى رقمي فقط"),
    ]

    LANGUAGE_CHOICES = [
        ("", "كل اللغات"),
        ("arabic", "العربية"),
        ("english", "الإنجليزية"),
    ]

    query = forms.CharField(required=False, label="كلمة البحث")
    search_scope = forms.ChoiceField(choices=SEARCH_SCOPE, required=False, initial="all", label="نطاق البحث")

    category = forms.ModelChoiceField(queryset=Category.objects.none(), required=False, label="الفئة")
    author = forms.ModelChoiceField(queryset=Author.objects.none(), required=False, label="المؤلف")
    publisher = forms.ModelChoiceField(queryset=Publisher.objects.none(), required=False, label="الناشر")

    min_pages = forms.IntegerField(required=False, min_value=1, label="أدنى صفحات")
    max_pages = forms.IntegerField(required=False, min_value=1, label="أقصى صفحات")
    year = forms.IntegerField(required=False, min_value=1000, max_value=2100, label="سنة النشر")
    language = forms.ChoiceField(required=False, choices=LANGUAGE_CHOICES, label="لغة الكتاب")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["category"].queryset = Category.objects.order_by("name")
        self.fields["author"].queryset = Author.objects.order_by("name")
        self.fields["publisher"].queryset = Publisher.objects.order_by("name")

        self.fields["category"].empty_label = "كل الفئات"
        self.fields["author"].empty_label = "كل المؤلفين"
        self.fields["publisher"].empty_label = "كل الناشرين"

        for field in self.fields.values():
            field.widget.attrs.update({"class": "input-field"})

        self.fields["query"].widget.attrs.update({"placeholder": "ابحث في جميع بيانات الكتاب: عنوان، مؤلف، فئة، ناشر، ISBN..."})
        self.fields["min_pages"].widget.attrs.update({"placeholder": "من"})
        self.fields["max_pages"].widget.attrs.update({"placeholder": "إلى"})
        self.fields["year"].widget.attrs.update({"placeholder": "مثال: 2024"})
