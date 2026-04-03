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


class Notification(models.Model):
    TYPE_OVERDUE = "overdue"
    TYPE_RESERVATION_CREATED = "reservation_created"
    TYPE_RESERVATION_APPROVED = "reservation_approved"
    TYPE_RESERVATION_AVAILABLE = "reservation_available"
    TYPE_HIGH_RISK_MEMBER = "high_risk_member"
    TYPE_PENDING_FINE = "pending_fine"
    TYPE_SUSPENDED_MEMBER = "suspended_member"
    TYPE_CHOICES = [
        (TYPE_OVERDUE, "استعارة متأخرة"),
        (TYPE_RESERVATION_CREATED, "طلب حجز جديد"),
        (TYPE_RESERVATION_APPROVED, "حجز تمت الموافقة عليه"),
        (TYPE_RESERVATION_AVAILABLE, "كتاب محجوز أصبح متاحًا"),
        (TYPE_HIGH_RISK_MEMBER, "إشعار عضو غير ملتزم"),
        (TYPE_PENDING_FINE, "غرامات غير مدفوعة"),
        (TYPE_SUSPENDED_MEMBER, "عضو موقوف"),
    ]

    notification_type = models.CharField(max_length=40, choices=TYPE_CHOICES, db_index=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    borrowing = models.ForeignKey(Borrowing, on_delete=models.CASCADE, null=True, blank=True)
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, null=True, blank=True)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.title


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

    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
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

