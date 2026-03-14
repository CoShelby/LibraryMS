from django.db import migrations, models


def forwards_map_member_level(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    Member.objects.filter(level__in=[1, "1"]).update(level="first")
    Member.objects.filter(level__in=[2, "2"]).update(level="second")
    Member.objects.filter(level__in=[3, "3"]).update(level="third")
    Member.objects.filter(level__in=[4, "4"]).update(level="fourth")


def backwards_map_member_level(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    Member.objects.filter(level="first").update(level="1")
    Member.objects.filter(level="second").update(level="2")
    Member.objects.filter(level="third").update(level="3")
    Member.objects.filter(level="fourth").update(level="4")


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0003_remove_member_barcode_or_qr"),
    ]

    operations = [
        migrations.AlterField(
            model_name="member",
            name="level",
            field=models.CharField(
                blank=True,
                choices=[
                    ("first", "الأول"),
                    ("second", "الثاني"),
                    ("third", "الثالث"),
                    ("fourth", "الرابع"),
                ],
                max_length=10,
                null=True,
            ),
        ),
        migrations.RunPython(forwards_map_member_level, backwards_map_member_level),
    ]
