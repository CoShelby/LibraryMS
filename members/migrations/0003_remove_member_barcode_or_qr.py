from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0002_rename_barcode_member_barcode_or_qr_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="member",
            name="barcode_or_qr",
        ),
    ]
