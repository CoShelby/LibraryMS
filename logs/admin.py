from django.contrib import admin

from .models import Log


@admin.register(Log)
class LogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "timestamp")
    search_fields = ("action", "user__username")
    list_filter = ("timestamp",)
