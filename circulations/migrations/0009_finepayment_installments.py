from django.db import migrations, models


def backfill_fine_payment_amount(apps, schema_editor):
    FinePayment = apps.get_model("circulations", "FinePayment")
    for payment in FinePayment.objects.select_related("fine").all():
        if payment.amount in (None, 0):
            payment.amount = max(getattr(payment.fine, "amount", 0), 0)
            payment.save(update_fields=["amount"])


def clear_fine_payment_amount(apps, schema_editor):
    FinePayment = apps.get_model("circulations", "FinePayment")
    FinePayment.objects.all().update(amount=0)


class Migration(migrations.Migration):

    dependencies = [
        ("circulations", "0008_reservation_approved_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="finepayment",
            name="amount",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="finepayment",
            name="external_reference",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AlterField(
            model_name="finepayment",
            name="fine",
            field=models.ForeignKey(on_delete=models.CASCADE, related_name="payments", to="circulations.fine"),
        ),
        migrations.RunPython(backfill_fine_payment_amount, clear_fine_payment_amount),
        migrations.AlterField(
            model_name="finepayment",
            name="amount",
            field=models.PositiveIntegerField(),
        ),
    ]
