from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0005_member_card_print_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="photo",
            field=models.ImageField(blank=True, null=True, upload_to="members/photos/"),
        ),
    ]
