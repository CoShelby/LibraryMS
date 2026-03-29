from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_admins',
    )
    is_admin = models.BooleanField(default=False)
    can_manage_admins = models.BooleanField(default=False)
    can_manage_books = models.BooleanField(default=False)
    can_manage_members = models.BooleanField(default=False)
    can_manage_circulation = models.BooleanField(default=False)
    can_manage_categories = models.BooleanField(default=False)

    def __str__(self):
        return self.username
