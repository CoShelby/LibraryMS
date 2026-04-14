from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.services import admin_capability_required, is_library_admin
from books.models import Book
from emails.member_messages import sync_automatic_member_messages
from members.models import Member

from .models import Borrowing, Fine, Reservation
from .services import (
    borrow_book,
    cancel_reservation,
    get_member_active_borrowings,
    get_member_active_reservations,
    get_member_borrowing_history,
    get_member_reservation_history,
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
            reserve_result = reserve_book(member, book)
            if reserve_result.get('created_renewal_request'):
                messages.success(request, 'Renewal request sent to administration.')
            else:
                messages.success(request, "تم إرسال طلب الحجز بنجاح، بانتظار موافقة الإدارة.")
        except Member.DoesNotExist:
            messages.error(request, "رقم العضوية غير صحيح.")
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect("book_detail", book.id)

    return render(request, "circulation/reserve.html", {"book": book})


def member_portal_view(request):
    sync_automatic_member_messages()
    membership_number = (request.GET.get("membership") or "").strip()
    member_id = (request.GET.get("member_id") or "").strip()

    member = None
    borrowings = []
    reservations = []
    borrowing_history = []
    reservation_history = []
    overdue_borrowings = []
    unpaid_fines = []

    is_admin_view = is_library_admin(request.user)

    if is_admin_view and member_id:
        try:
            member = Member.objects.get(id=int(member_id))
            membership_number = member.membership_number
        except (ValueError, Member.DoesNotExist):
            messages.error(request, "تعذر العثور على العضو المطلوب.")
    elif membership_number:
        try:
            member = Member.objects.get(membership_number=membership_number)
        except Member.DoesNotExist:
            messages.error(request, "رقم العضوية غير موجود.")

    if member:
        borrowings = get_member_active_borrowings(member)
        reservations = get_member_active_reservations(member)
        borrowing_history = get_member_borrowing_history(member).filter(return_date__isnull=False)
        reservation_history = get_member_reservation_history(member).exclude(status__in=["pending", "approved"])
        overdue_borrowings = borrowings.filter(due_date__lt=timezone.now())
        unpaid_fines = Fine.objects.select_related("borrowing__book_copy__book").filter(
            borrowing__member=member,
            paid=False,
        )

    return render(
        request,
        "circulation/member_portal.html",
        {
            "member": member,
            "borrowings": borrowings,
            "reservations": reservations,
            "borrowing_history": borrowing_history,
            "reservation_history": reservation_history,
            "membership": membership_number,
            "is_admin_view": is_admin_view,
            "overdue_borrowings": overdue_borrowings,
            "unpaid_fines": unpaid_fines,
            "unpaid_fines_total": sum((fine.amount for fine in unpaid_fines), 0),
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

