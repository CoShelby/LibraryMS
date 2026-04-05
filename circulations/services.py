from django.utils import timezone

from books.models import BookCopy

from .models import Borrowing, Fine, Reservation
from .timing import (
    calculate_fine_snapshot,
    fine_unit_label,
    get_borrow_duration,
    get_reservation_duration,
)
from dashboard.notifications import (
    create_reservation_approved_notification,
    create_reservation_created_notification,
    notify_reserved_book_available,
)

MAX_BORROW_LIMIT = 3


def get_active_borrows_count(member):
    return Borrowing.objects.filter(member=member, return_date__isnull=True).count()


def _expire_pending_reservations():
    now = timezone.now()
    Reservation.objects.filter(
        status__in=["pending", "approved"],
        cancel_date__isnull=False,
        cancel_date__lt=now,
    ).update(status="cancelled")


def can_member_borrow(member):
    return get_active_borrows_count(member) < MAX_BORROW_LIMIT


def _book_supply(book):
    usable_copies = BookCopy.objects.filter(book=book, status="new").count()
    active_borrowings = Borrowing.objects.filter(book_copy__book=book, return_date__isnull=True).count()
    approved_reservations = Reservation.objects.filter(book=book, status="approved").count()
    available_after_reservations = max(usable_copies - active_borrowings - approved_reservations, 0)
    return {
        "usable_copies": usable_copies,
        "active_borrowings": active_borrowings,
        "approved_reservations": approved_reservations,
        "available_after_reservations": available_after_reservations,
    }


def get_book_available_copies(book):
    return _book_supply(book)["available_after_reservations"]


def _find_available_copy(book, preferred_copy=None):
    active_copy_ids = Borrowing.objects.filter(book_copy__book=book, return_date__isnull=True).values_list(
        "book_copy_id", flat=True
    )

    if preferred_copy:
        if preferred_copy.book_id != book.id:
            raise ValueError("هذه النسخة لا تتبع للكتاب المحدد.")
        if preferred_copy.status != "new":
            raise ValueError("حالة النسخة لا تسمح بالاستعارة.")
        if preferred_copy.id in active_copy_ids:
            raise ValueError("هذه النسخة مستعارة بالفعل.")
        return preferred_copy

    return (
        BookCopy.objects.filter(book=book, status="new")
        .exclude(id__in=active_copy_ids)
        .order_by("id")
        .first()
    )


def borrow_book(member, book, employee, preferred_copy=None):
    _expire_pending_reservations()

    if member.is_suspended:
        raise ValueError("هذا العضو موقوف عن الاستعارة.")

    if not can_member_borrow(member):
        raise ValueError("لا يمكن استعارة أكثر من 3 كتب في نفس الوقت.")

    member_approved_reservation = (
        Reservation.objects.filter(member=member, book=book, status="approved").order_by("reservation_date").first()
    )

    if not member_approved_reservation and get_book_available_copies(book) <= 0:
        raise ValueError("لا توجد نسخ متاحة حاليًا.")

    copy = _find_available_copy(book, preferred_copy=preferred_copy)
    if not copy:
        raise ValueError("لا توجد نسخة صالحة للاستعارة.")

    now = timezone.now()
    due_date = now + get_borrow_duration()

    # نستخدم التاريخ والوقت معًا لدعم وضع العرض التجريبي بالدقائق.
    borrowing = Borrowing.objects.create(
        member=member,
        book_copy=copy,
        employee=employee,
        created_by=employee,
        borrow_date=now,
        due_date=due_date,
        renewed=False,
        renewal_requested=False,
    )

    if member_approved_reservation:
        member_approved_reservation.status = "completed"
        member_approved_reservation.related_borrow = borrowing
        member_approved_reservation.save(update_fields=["status", "related_borrow"])

    return borrowing


def renew_borrowing(borrowing):
    _expire_pending_reservations()

    if borrowing.return_date:
        raise ValueError("لا يمكن تجديد إعارة تم إرجاعها.")

    if borrowing.renewed:
        raise ValueError("تم تجديد هذه الإعارة مسبقًا.")

    # تمنع تجديد الاستعارة فقط إذا كان هناك حجز معتمد (approved) على هذا الكتاب
    # الحجز المعلق (pending) وحده لا يمنع التجديد
    if Reservation.objects.filter(book=borrowing.book_copy.book, status="approved").exists():
        raise ValueError("لا يمكن تجديد الإعارة لوجود حجز معتمد على هذا الكتاب بانتظار عضو آخر.")

    borrowing.due_date = borrowing.due_date + get_borrow_duration()
    borrowing.renewed = True
    borrowing.renewal_requested = False
    borrowing.save(update_fields=["due_date", "renewed", "renewal_requested"])
    return borrowing


def request_renewal(borrowing):
    if borrowing.return_date:
        raise ValueError("لا يمكن طلب تجديد لإعارة منتهية.")

    if borrowing.renewed:
        raise ValueError("تم تجديد هذه الإعارة مسبقًا.")

    if borrowing.renewal_requested:
        raise ValueError("تم إرسال طلب تجديد مسبقًا.")

    borrowing.renewal_requested = True
    borrowing.save(update_fields=["renewal_requested"])
    return borrowing


def reject_renewal_request(borrowing):
    if not borrowing.renewal_requested:
        raise ValueError("لا يوجد طلب تجديد معلق.")

    borrowing.renewal_requested = False
    borrowing.save(update_fields=["renewal_requested"])
    return borrowing


def return_book(borrowing):
    if borrowing.return_date:
        raise ValueError("تم إرجاع هذا الكتاب مسبقًا.")

    borrowing.return_date = timezone.now()
    borrowing.renewal_requested = False
    borrowing.save(update_fields=["return_date", "renewal_requested"])

    fine = None
    fine_snapshot = calculate_fine_snapshot(borrowing.due_date, reference_time=borrowing.return_date)
    if fine_snapshot["has_fine"]:
        fine = Fine.objects.create(
            borrowing=borrowing,
            days_late=fine_snapshot["units"],
            amount=fine_snapshot["amount"],
        )

    notify_reserved_book_available(borrowing.book_copy.book)
    return fine


def reserve_book(member, book):
    _expire_pending_reservations()

    # الحجز مسموح فقط للكتب الورقية التي لديها نسخة واحدة على الأقل.
    if not BookCopy.objects.filter(book=book).exists():
        raise ValueError("لا يمكن حجز كتاب رقمي فقط بدون نسخة ورقية.")

    usable_copies = BookCopy.objects.filter(book=book, status="new").count()
    active_borrowings = Borrowing.objects.filter(book_copy__book=book, return_date__isnull=True).count()
    if (usable_copies - active_borrowings) > 0:
        raise ValueError("يوجد نسخ متاحة حالياً للاستعارة. الأولوية للحضور الشخصي ولا يُسمح بالحجز إذا كان الكتاب متوفراً.")

    if Reservation.objects.filter(member=member, book=book, status__in=["pending", "approved"]).exists():
        raise ValueError("لديك طلب حجز نشط مسبقًا لنفس الكتاب.")

    active_reservations = Reservation.objects.filter(member=member, status__in=["pending", "approved"]).count()
    if active_reservations >= 3:
        raise ValueError("لا يمكن تقديم أكثر من 3 طلبات حجز نشطة.")

    reservation = Reservation.objects.create(
        member=member,
        book=book,
        status="pending",
        cancel_date=timezone.now() + get_reservation_duration(),
    )
    create_reservation_created_notification(reservation)
    return reservation


def approve_reservation(reservation):
    _expire_pending_reservations()

    if reservation.status != "pending":
        raise ValueError("لا يمكن اعتماد هذا الحجز.")

    # الاعتماد لا يتطلب وجود نسخة متاحة - الحجز هو طابور انتظار حتى يتم إرجاع نسخة
    reservation.status = "approved"
    reservation.save(update_fields=["status"])
    create_reservation_approved_notification(reservation)
    return reservation


def cancel_reservation(reservation):
    _expire_pending_reservations()

    if reservation.status not in {"pending", "approved"}:
        raise ValueError("لا يمكن إلغاء هذا الحجز.")

    reservation.status = "cancelled"
    reservation.cancel_date = timezone.now()
    reservation.save(update_fields=["status", "cancel_date"])
    return reservation


def complete_reservation(reservation, employee=None):
    _expire_pending_reservations()

    if reservation.status == "pending":
        approve_reservation(reservation)
        reservation.refresh_from_db()

    if reservation.status != "approved":
        raise ValueError("الحجز غير معتمد ولا يمكن إتمام الاستعارة.")

    borrowing = borrow_book(reservation.member, reservation.book, employee)
    reservation.related_borrow = borrowing
    reservation.status = "completed"
    reservation.save(update_fields=["related_borrow", "status"])
    return borrowing


def get_member_active_borrowings(member):
    _expire_pending_reservations()
    return Borrowing.objects.select_related("book_copy__book").filter(member=member, return_date__isnull=True)


def get_member_active_reservations(member):
    _expire_pending_reservations()
    return Reservation.objects.select_related("book").filter(member=member, status__in=["pending", "approved"])


def get_member_borrowing_history(member):
    return Borrowing.objects.select_related("book_copy__book").filter(member=member).order_by("-borrow_date", "-id")


def get_member_reservation_history(member):
    return Reservation.objects.select_related("book").filter(member=member).order_by("-reservation_date", "-id")


def describe_fine_units(units):
    return f"{units} {fine_unit_label(units)}"

