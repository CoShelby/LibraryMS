from django.db import migrations, models


def forwards_reservation_status(apps, schema_editor):
    Reservation = apps.get_model("circulations", "Reservation")
    Reservation.objects.filter(status="active").update(status="pending")
    Reservation.objects.filter(status="expired").update(status="cancelled")
    Reservation.objects.filter(status__isnull=True).update(status="pending")
    Reservation.objects.filter(status="").update(status="pending")


def backwards_reservation_status(apps, schema_editor):
    Reservation = apps.get_model("circulations", "Reservation")
    Reservation.objects.filter(status="pending").update(status="active")
    Reservation.objects.filter(status="approved").update(status="active")


class Migration(migrations.Migration):

    dependencies = [
        ("circulations", "0003_fix_reservation_status_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="borrowing",
            name="renewal_requested",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(forwards_reservation_status, backwards_reservation_status),
        migrations.AlterField(
            model_name="reservation",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "طلب حجز"),
                    ("approved", "حجز معتمد"),
                    ("completed", "تمت الاستعارة"),
                    ("cancelled", "ملغي"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
