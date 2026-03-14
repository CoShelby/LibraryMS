from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0004_category_translation_and_language"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="book",
            name="serial_number",
        ),
    ]
