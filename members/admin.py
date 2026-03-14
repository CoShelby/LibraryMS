from django.contrib import admin

from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "membership_number", "member_type", "membership_expiry")
    search_fields = ("name", "membership_number", "university_id")
    list_filter = ("member_type",)
