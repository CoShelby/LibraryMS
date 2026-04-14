from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("circulations", "0007_alter_borrowing_employee"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]