from django.contrib import admin

from .models import DigitalLibrary


@admin.register(DigitalLibrary)
class DigitalLibraryAdmin(admin.ModelAdmin):
    list_display = ("book",)
    search_fields = ("book__title",)
