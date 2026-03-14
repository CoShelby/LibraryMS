from django.contrib import admin

from .models import Borrowing, Fine, Loan, Reservation


@admin.register(Borrowing)
class BorrowingAdmin(admin.ModelAdmin):
    list_display = ("book_copy", "member", "borrow_date", "due_date", "return_date")
    search_fields = ("book_copy__book__title", "member__name")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("book", "member", "status", "reservation_date")
    search_fields = ("book__title", "member__name")
    list_filter = ("status",)


@admin.register(Fine)
class FineAdmin(admin.ModelAdmin):
    list_display = ("borrowing", "amount", "days_late", "paid", "created_at")
    list_filter = ("paid",)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("user", "book", "due_date", "returned")
    list_filter = ("returned",)
