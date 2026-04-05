from django.db import models

from accounts.models import User
from members.models import Member
from notifications.models import Notification


class MemberMessageLog(models.Model):
    MESSAGE_OVERDUE = "overdue"
    MESSAGE_RESERVATION_APPROVED = "reservation_approved"
    MESSAGE_BOOK_AVAILABLE = "book_available"
    MESSAGE_PENDING_FINE = "pending_fines"
    MESSAGE_SUSPENSION_WARNING = "suspension_warning"
    MESSAGE_GENERAL = "general"
    MESSAGE_CHOICES = [
        (MESSAGE_OVERDUE, "Overdue books"),
        (MESSAGE_RESERVATION_APPROVED, "Reservation approved"),
        (MESSAGE_BOOK_AVAILABLE, "Book available"),
        (MESSAGE_PENDING_FINE, "Pending fines"),
        (MESSAGE_SUSPENSION_WARNING, "Suspension warning"),
        (MESSAGE_GENERAL, "General"),
    ]

    # Removed SMS logic as per requirement #8.
    CHANNEL_EMAIL = "email"
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
    ]

    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_PREPARED = "prepared"
    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_PREPARED, "Prepared"),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="message_logs")
    notification = models.ForeignKey(Notification, on_delete=models.SET_NULL, null=True, blank=True)
    message_type = models.CharField(max_length=40, choices=MESSAGE_CHOICES, db_index=True)
    channel = models.CharField(max_length=16, choices=CHANNEL_CHOICES, db_index=True)
    recipient = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True, default="")
    body = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PREPARED, db_index=True)
    error_message = models.TextField(blank=True, default="")
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_member_messages")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.member.name} - {self.message_type} ({self.channel})"
