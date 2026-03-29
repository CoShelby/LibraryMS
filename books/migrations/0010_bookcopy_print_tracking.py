from django.db import migrations, models
from django.utils import timezone


def mark_existing_copies_printed(apps, schema_editor):
    BookCopy = apps.get_model("books", "BookCopy")
    BookCopy.objects.all().update(is_printed=True)


class Migration(migrations.Migration):

    dependencies = [
        ("books", "0009_rename_books_book_title_view_idx_books_book_title_28b4f4_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookcopy",
            name="is_printed",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="bookcopy",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name="bookcopy",
            index=models.Index(fields=["book", "is_printed", "-created_at"], name="books_copy_qr_idx"),
        ),
        migrations.RunPython(mark_existing_copies_printed, migrations.RunPython.noop),
    ]
