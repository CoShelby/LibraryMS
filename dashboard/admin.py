from django.contrib import admin

from .models import LibraryBranding


@admin.register(LibraryBranding)
class LibraryBrandingAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at")

