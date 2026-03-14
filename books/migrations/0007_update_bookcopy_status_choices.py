from django.db import migrations, models


def forwards_map_bookcopy_status(apps, schema_editor):
    BookCopy = apps.get_model("books", "BookCopy")
    BookCopy.objects.filter(status__in=["available", "borrowed", "reserved", ""]).update(status="new")
    BookCopy.objects.filter(status__isnull=True).update(status="new")


def backwards_map_bookcopy_status(apps, schema_editor):
    BookCopy = apps.get_model("books", "BookCopy")
    BookCopy.objects.filter(status="new").update(status="available")


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0006_alter_bookcopy_barcode"),
    ]

    operations = [
        migrations.RunPython(forwards_map_bookcopy_status, backwards_map_bookcopy_status),
        migrations.AlterField(
            model_name="bookcopy",
            name="status",
            field=models.CharField(
                choices=[("new", "جديد"), ("damaged", "تالف")],
                default="new",
                max_length=20,
            ),
        ),
    ]
