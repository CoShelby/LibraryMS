from django.db import migrations


SEEDED_CATEGORY_IDS = [
    "CS_GENERAL",
    "CS_PROGRAMMING",
    "CS_ALGORITHMS",
    "CS_AI",
    "CS_SECURITY",
    "CS_NETWORKS",
    "IT_SYSTEMS",
    "IT_DATABASES",
    "IT_CLOUD",
    "IT_SOFTWARE",
]


def remove_unused_seeded_categories(apps, schema_editor):
    Category = apps.get_model("books", "Category")
    Book = apps.get_model("books", "Book")

    for category in Category.objects.filter(category_id__in=SEEDED_CATEGORY_IDS):
        if not Book.objects.filter(category_id=category.id).exists():
            category.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0014_book_identifiers"),
    ]

    operations = [
        migrations.RunPython(remove_unused_seeded_categories, migrations.RunPython.noop),
    ]
