from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0006_remove_notification_borrowing_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="LibrarySystemSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fine_amount_per_unit", models.PositiveIntegerField(default=1000)),
                ("reservation_days", models.PositiveIntegerField(default=2)),
                ("borrow_days", models.PositiveIntegerField(default=3)),
                ("email_host", models.CharField(default="smtp.gmail.com", max_length=255)),
                ("email_port", models.PositiveIntegerField(default=587)),
                ("email_use_tls", models.BooleanField(default=True)),
                ("email_host_user", models.EmailField(blank=True, default="", max_length=254)),
                ("email_host_password", models.CharField(blank=True, default="", max_length=255)),
                ("default_from_email", models.EmailField(blank=True, default="", max_length=254)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Library system settings",
                "verbose_name_plural": "Library system settings",
            },
        ),
    ]
