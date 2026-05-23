from django.contrib import admin

from .models import LibraryBranding, LibrarySystemSettings


@admin.register(LibraryBranding)
class LibraryBrandingAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at")


@admin.register(LibrarySystemSettings)
class LibrarySystemSettingsAdmin(admin.ModelAdmin):
    list_display = ("fine_amount_per_unit", "reservation_days", "borrow_days", "email_host_user", "updated_at")

