from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class LibraryUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Library Access",
            {
                "fields": (
                    "is_admin",
                    "can_manage_admins",
                    "can_manage_books",
                    "can_manage_members",
                    "can_manage_circulation",
                    "can_manage_categories",
                )
            },
        ),
    )

    list_display = (
        "username",
        "email",
        "is_staff",
        "is_admin",
        "can_manage_admins",
        "can_manage_books",
        "can_manage_members",
        "can_manage_circulation",
        "can_manage_categories",
    )
