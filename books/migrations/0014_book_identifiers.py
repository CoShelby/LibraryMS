from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0013_categorysearchstat"),
    ]

    operations = [
        migrations.AddField(
            model_name="book",
            name="isbn",
            field=models.CharField(blank=True, db_index=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="book",
            name="doi",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
    ]
