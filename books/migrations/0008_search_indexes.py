from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0007_update_bookcopy_status_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="author",
            name="name",
            field=models.CharField(db_index=True, max_length=200),
        ),
        migrations.AlterField(
            model_name="book",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name="book",
            name="dewey_decimal_number",
            field=models.CharField(db_index=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="book",
            name="language",
            field=models.CharField(choices=[("arabic", "العربية"), ("english", "الإنجليزية")], db_index=True, default="arabic", max_length=20),
        ),
        migrations.AlterField(
            model_name="book",
            name="title",
            field=models.CharField(db_index=True, max_length=300),
        ),
        migrations.AlterField(
            model_name="book",
            name="view_count",
            field=models.PositiveIntegerField(db_index=True, default=0),
        ),
        migrations.AlterField(
            model_name="category",
            name="name",
            field=models.CharField(db_index=True, max_length=200),
        ),
        migrations.AlterField(
            model_name="category",
            name="name_en",
            field=models.CharField(blank=True, db_index=True, default="", max_length=200),
        ),
        migrations.AlterField(
            model_name="publisher",
            name="name",
            field=models.CharField(db_index=True, max_length=200),
        ),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["title", "view_count"], name="books_book_title_view_idx"),
        ),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["language", "publication_year"], name="books_book_lang_year_idx"),
        ),
    ]
