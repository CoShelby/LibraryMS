from django.db import migrations, models


def normalize_categories_and_languages(apps, schema_editor):
    Category = apps.get_model("books", "Category")
    Book = apps.get_model("books", "Book")

    category_map = {
        "CS_GENERAL": ("علوم الحاسوب", "Computer Science"),
        "CS_PROGRAMMING": ("البرمجة", "Programming"),
        "CS_ALGORITHMS": ("الخوارزميات وهياكل البيانات", "Algorithms and Data Structures"),
        "CS_AI": ("الذكاء الاصطناعي", "Artificial Intelligence"),
        "CS_SECURITY": ("الأمن السيبراني", "Cybersecurity"),
        "CS_NETWORKS": ("شبكات الحاسوب", "Computer Networks"),
        "IT_SYSTEMS": ("نظم المعلومات", "Information Systems"),
        "IT_DATABASES": ("قواعد البيانات", "Database Systems"),
        "IT_CLOUD": ("الحوسبة السحابية", "Cloud Computing"),
        "IT_SOFTWARE": ("هندسة البرمجيات", "Software Engineering"),
    }

    for category in Category.objects.all():
        if category.category_id in category_map:
            name_ar, name_en = category_map[category.category_id]
            category.name = name_ar
            category.name_en = name_en
        elif not category.name_en:
            category.name_en = category.name
        category.save(update_fields=["name", "name_en"])

    for book in Book.objects.all():
        value = (book.language or "").strip().lower()
        if value in {"arabic", "ar", "العربية"}:
            book.language = "arabic"
        elif value in {"english", "en", "الانجليزية", "الإنجليزية"}:
            book.language = "english"
        else:
            book.language = "arabic"
        book.save(update_fields=["language"])


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0003_seed_cs_it_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="name_en",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AlterField(
            model_name="category",
            name="category_id",
            field=models.CharField(blank=True, max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name="book",
            name="language",
            field=models.CharField(
                choices=[("arabic", "العربية"), ("english", "الإنجليزية")],
                default="arabic",
                max_length=20,
            ),
        ),
        migrations.RunPython(normalize_categories_and_languages, migrations.RunPython.noop),
    ]
