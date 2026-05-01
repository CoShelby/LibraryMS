from django.db import models
from django.db.models import Sum

from accounts.models import User
from books.models import Book, BookCopy
from members.models import Member


class Borrowing(models.Model):
    borrowing_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    book_copy = models.ForeignKey(BookCopy, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    employee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='employee_borrowings')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_borrowings')
    borrow_date = models.DateTimeField()
    due_date = models.DateTimeField()
    return_date = models.DateTimeField(blank=True, null=True)
    renewed = models.BooleanField(default=False)
    renewal_requested = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.member.name} - {self.book_copy.book.title}"


class Reservation(models.Model):
    STATUS = (
        ("pending", "طلب حجز"),
        ("approved", "حجز معتمد"),
        ("completed", "تمت الاستعارة"),
        ("cancelled", "ملغي"),
    )

    reservation_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    reservation_date = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    cancel_date = models.DateTimeField(null=True, blank=True)
    related_borrow = models.ForeignKey(Borrowing, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")

    def __str__(self):
        return f"{self.book.title} - {self.member.name}"


class Fine(models.Model):
    borrowing = models.OneToOneField(Borrowing, on_delete=models.CASCADE)
    days_late = models.IntegerField()
    amount = models.IntegerField()
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_paid_amount(self):
        if "payments" in getattr(self, "_prefetched_objects_cache", {}):
            return sum(payment.amount for payment in self.payments.all())
        return self.payments.aggregate(total=Sum("amount")).get("total") or 0

    @property
    def unpaid_amount(self):
        return max(self.amount - self.total_paid_amount, 0)

    def sync_paid_status(self, save=True):
        next_paid_value = self.unpaid_amount == 0
        if self.paid != next_paid_value:
            self.paid = next_paid_value
            if save:
                self.save(update_fields=["paid"])
        return self.paid

    def __str__(self):
        return f"{self.amount}"


class FinePayment(models.Model):
    fine = models.ForeignKey(Fine, on_delete=models.CASCADE, related_name="payments")
    amount = models.PositiveIntegerField()
    external_reference = models.CharField(max_length=120, blank=True, default="")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_fine_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment for Fine #{self.fine_id}"


class Loan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    reservation = models.ForeignKey(Reservation, on_delete=models.SET_NULL, null=True, blank=True)
    borrow_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField()
    returned = models.BooleanField(default=False)
