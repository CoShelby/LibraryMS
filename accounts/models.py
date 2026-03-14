from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    is_admin = models.BooleanField(default=False)
    can_manage_admins = models.BooleanField(default=False)
    can_manage_books = models.BooleanField(default=False)
    can_manage_members = models.BooleanField(default=False)
    can_manage_circulation = models.BooleanField(default=False)
    can_manage_categories = models.BooleanField(default=False)

    def __str__(self):
        return self.username
