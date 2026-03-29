from django.db import models

from circulations.models import Borrowing, Reservation


class Notification(models.Model):
    TYPE_OVERDUE = "overdue"
    TYPE_RESERVATION_CREATED = "reservation_created"
    TYPE_RESERVATION_AVAILABLE = "reservation_available"
    TYPE_CHOICES = [
        (TYPE_OVERDUE, "استعارة متأخرة"),
        (TYPE_RESERVATION_CREATED, "طلب حجز جديد"),
        (TYPE_RESERVATION_AVAILABLE, "كتاب محجوز أصبح متاحًا"),
    ]

    notification_type = models.CharField(max_length=40, choices=TYPE_CHOICES, db_index=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    borrowing = models.ForeignKey(Borrowing, on_delete=models.CASCADE, null=True, blank=True)
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title