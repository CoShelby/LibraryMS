from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("circulations", "0004_add_renewal_requested_and_update_reservation_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="borrowing",
            name="borrow_date",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="borrowing",
            name="due_date",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="borrowing",
            name="return_date",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
