import os

from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_primary_admin(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    if User.objects.filter(pk=1).exists():
        User.objects.filter(pk=1).update(
            is_staff=True,
            is_superuser=True,
            is_admin=True,
            can_manage_admins=True,
            can_manage_books=True,
            can_manage_members=True,
            can_manage_circulation=True,
            can_manage_categories=True,
            is_active=True,
        )
        return

    username = os.getenv("INITIAL_ADMIN_USERNAME", "admin")
    if User.objects.filter(username__iexact=username).exists():
        username = "primary-admin"
    suffix = 1
    base_username = username
    while User.objects.filter(username__iexact=username).exists():
        suffix += 1
        username = f"{base_username}-{suffix}"

    User.objects.create(
        pk=1,
        username=username,
        email=os.getenv("INITIAL_ADMIN_EMAIL", "admin@example.com"),
        password=make_password(os.getenv("INITIAL_ADMIN_PASSWORD", "Admin@12345")),
        is_staff=True,
        is_superuser=True,
        is_admin=True,
        can_manage_admins=True,
        can_manage_books=True,
        can_manage_members=True,
        can_manage_circulation=True,
        can_manage_categories=True,
        is_active=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_created_by"),
    ]

    operations = [
        migrations.RunPython(create_primary_admin, migrations.RunPython.noop),
    ]
