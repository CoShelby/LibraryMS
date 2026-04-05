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




