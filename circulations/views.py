from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.services import admin_capability_required
from books.models import Book
from members.models import Member

from .models import Borrowing, Reservation
from .services import (
    borrow_book,
    cancel_reservation,
    get_member_active_borrowings,
    get_member_active_reservations,
    request_renewal,
    reserve_book,
)


@admin_capability_required("can_manage_circulation")
def borrow_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)

    if request.method == "POST":
        membership_number = (request.POST.get("membership") or "").strip()

        try:
            member = Member.objects.get(membership_number=membership_number)
            borrow_book(member, book, request.user if request.user.is_authenticated else None)
            messages.success(request, "تمت الاستعارة بنجاح.")
        except Member.DoesNotExist:
            messages.error(request, "رقم العضوية غير صحيح.")
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect("book_detail", book.id)

    return render(request, "circulation/borrow.html", {"book": book})


def reserve_view(request, book_id):
    book = get_object_or_404(Book, id=book_id)

    if request.method == "POST":
        membership_number = (request.POST.get("membership") or "").strip()

        try:
            member = Member.objects.get(membership_number=membership_number)
            reserve_book(member, book)
            messages.success(request, "تم إرسال طلب الحجز بنجاح، بانتظار موافقة الإدارة.")
        except Member.DoesNotExist:
            messages.error(request, "رقم العضوية غير صحيح.")
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect("book_detail", book.id)

    return render(request, "circulation/reserve.html", {"book": book})


def member_portal_view(request):
    membership_number = (request.GET.get("membership") or "").strip()
    member = None
    borrowings = []
    reservations = []

    if membership_number:
        try:
            member = Member.objects.get(membership_number=membership_number)
            borrowings = get_member_active_borrowings(member)
            reservations = get_member_active_reservations(member)
        except Member.DoesNotExist:
            messages.error(request, "رقم العضوية غير موجود.")

    return render(
        request,
        "circulation/member_portal.html",
        {
            "member": member,
            "borrowings": borrowings,
            "reservations": reservations,
            "membership": membership_number,
        },
    )


def renew_borrowing_view(request, borrowing_id):
    borrowing = get_object_or_404(Borrowing, id=borrowing_id)

    if request.method == "POST":
        membership_number = (request.POST.get("membership") or "").strip()

        if borrowing.member.membership_number != membership_number:
            messages.error(request, "لا يمكن تقديم طلب تجديد لهذه الإعارة بهذا الرقم.")
            return redirect(f"{request.META.get('HTTP_REFERER', '/')}")

        try:
            request_renewal(borrowing)
            messages.success(request, "تم إرسال طلب التجديد إلى الإدارة.")
        except ValueError as exc:
            messages.error(request, str(exc))

    return redirect(f"{request.META.get('HTTP_REFERER', '/')}")


def cancel_reservation_view(request, reservation_id):
    reservation = get_object_or_404(Reservation.objects.select_related("member"), id=reservation_id)

    if request.method == "POST":
        membership_number = (request.POST.get("membership") or "").strip()

        if reservation.member.membership_number != membership_number:
            messages.error(request, "لا يمكن إلغاء هذا الحجز بهذا الرقم.")
            return redirect(f"{request.META.get('HTTP_REFERER', '/')}")

        try:
            cancel_reservation(reservation)
            messages.success(request, "تم إلغاء طلب الحجز.")
        except ValueError as exc:
            messages.error(request, str(exc))

    return redirect(f"{request.META.get('HTTP_REFERER', '/')}")
