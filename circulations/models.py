from django.db import models

from accounts.models import User
from books.models import Book, BookCopy
from members.models import Member


class Borrowing(models.Model):
    borrowing_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    book_copy = models.ForeignKey(BookCopy, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    employee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    borrow_date = models.DateField()
    due_date = models.DateField()
    return_date = models.DateField(blank=True, null=True)
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

    def __str__(self):
        return f"{self.amount}"


class Loan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    reservation = models.ForeignKey(Reservation, on_delete=models.SET_NULL, null=True, blank=True)
    borrow_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField()
    returned = models.BooleanField(default=False)
