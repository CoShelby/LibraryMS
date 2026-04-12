from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("digital_library", "0002_digitallibrary_delete_digitalbook"),
    ]

    operations = [
        migrations.AlterField(
            model_name="digitallibrary",
            name="pdf_file",
            field=models.FileField(blank=True, null=True, upload_to="books/pdfs/"),
        ),
    ]
