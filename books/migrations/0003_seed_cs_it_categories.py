from django.db import migrations


def seed_categories(apps, schema_editor):
    Category = apps.get_model("books", "Category")
    defaults = [
        ("CS_GENERAL", "Computer Science", "CS-01"),
        ("CS_PROGRAMMING", "Programming", "CS-02"),
        ("CS_ALGORITHMS", "Algorithms and Data Structures", "CS-03"),
        ("CS_AI", "Artificial Intelligence", "CS-04"),
        ("CS_SECURITY", "Cybersecurity", "CS-05"),
        ("CS_NETWORKS", "Computer Networks", "CS-06"),
        ("IT_SYSTEMS", "Information Systems", "IT-01"),
        ("IT_DATABASES", "Database Systems", "IT-02"),
        ("IT_CLOUD", "Cloud Computing", "IT-03"),
        ("IT_SOFTWARE", "Software Engineering", "IT-04"),
    ]

    for category_id, name, shelf_location in defaults:
        Category.objects.get_or_create(
            category_id=category_id,
            defaults={"name": name, "shelf_location": shelf_location},
        )


def unseed_categories(apps, schema_editor):
    Category = apps.get_model("books", "Category")
    ids = [
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
    Category.objects.filter(category_id__in=ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0002_publisher_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
