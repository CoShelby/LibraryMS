from django.db import models
from django.templatetags.static import static

from accounts.models import User
from circulations.models import Borrowing, Reservation
from members.models import Member


class LibraryBranding(models.Model):
    name = models.CharField(max_length=255, default="نظام إدارة المكتبة")
    tagline = models.CharField(max_length=255, blank=True, default="")
    logo = models.ImageField(upload_to="branding/", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def logo_url(self):
        if self.logo:
            return self.logo.url
        return static("images/logo.jpg")



class LibrarySystemSettings(models.Model):
    fine_amount_per_unit = models.PositiveIntegerField(default=1000)
    reservation_days = models.PositiveIntegerField(default=2)
    borrow_days = models.PositiveIntegerField(default=3)
    email_host = models.CharField(max_length=255, default="smtp.gmail.com")
    email_port = models.PositiveIntegerField(default=587)
    email_use_tls = models.BooleanField(default=True)
    email_host_user = models.EmailField(blank=True, default="")
    email_host_password = models.CharField(max_length=255, blank=True, default="")
    default_from_email = models.EmailField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Library system settings"
        verbose_name_plural = "Library system settings"

    def __str__(self):
        return "Library system settings"

