from django.contrib import admin
from .models import MemberMessageLog

@admin.register(MemberMessageLog)
class MemberMessageLogAdmin(admin.ModelAdmin):
    list_display = ("member", "message_type", "channel", "status", "created_at")
    list_filter = ("message_type", "channel", "status", "created_at")
    search_fields = ("member__name", "recipient", "subject")
