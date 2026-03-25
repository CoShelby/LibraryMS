from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0004_update_level_choices"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="card_print_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="member",
            name="last_card_printed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
