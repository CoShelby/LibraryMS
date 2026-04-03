from django.contrib import admin

from .models import LibraryBranding, MemberMessageLog, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "notification_type", "member", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("title", "message", "member__name")


@admin.register(MemberMessageLog)
class MemberMessageLogAdmin(admin.ModelAdmin):
    list_display = ("member", "message_type", "channel", "status", "created_at")
    list_filter = ("message_type", "channel", "status", "created_at")
    search_fields = ("member__name", "recipient", "subject")


@admin.register(LibraryBranding)
class LibraryBrandingAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at")

