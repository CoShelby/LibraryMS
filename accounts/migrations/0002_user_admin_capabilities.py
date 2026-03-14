from django.db import migrations, models


def grant_full_access_to_existing_admins(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_superuser=True).update(
        can_manage_admins=True,
        can_manage_books=True,
        can_manage_members=True,
        can_manage_circulation=True,
        can_manage_categories=True,
    )
    User.objects.filter(is_superuser=False, is_staff=True).update(
        can_manage_admins=True,
        can_manage_books=True,
        can_manage_members=True,
        can_manage_circulation=True,
        can_manage_categories=True,
    )
    User.objects.filter(is_superuser=False, is_staff=False, is_admin=True).update(
        can_manage_admins=True,
        can_manage_books=True,
        can_manage_members=True,
        can_manage_circulation=True,
        can_manage_categories=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="can_manage_admins",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="can_manage_books",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="can_manage_categories",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="can_manage_circulation",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="can_manage_members",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(grant_full_access_to_existing_admins, migrations.RunPython.noop),
    ]
