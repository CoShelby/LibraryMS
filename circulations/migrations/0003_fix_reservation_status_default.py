from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("circulations", "0002_rename_copy_borrowing_book_copy_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reservation",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
