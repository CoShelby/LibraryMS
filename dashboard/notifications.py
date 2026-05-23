from django.db.models import Count, F, Q, Sum
from django.urls import reverse
from django.utils import timezone

from accounts.services import is_primary_admin
from books.models import BookCopy
from circulations.models import Borrowing, Fine, Reservation
from circulations.timing import calculate_fine_snapshot, get_reservation_duration
from emails.member_messages import send_member_message, sync_automatic_member_messages
from members.models import Member

from notifications.models import Notification


def _format_overdue_duration(delay):
    total_seconds = max(int(delay.total_seconds()), 0)
    days, remaining = divmod(total_seconds, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, _ = divmod(remaining, 60)

    parts = []
    if days:
        parts.append(f"{days} يوم")
    if hours:
        parts.append(f"{hours} ساعة")
    if minutes or not parts:
        parts.append(f"{minutes} دقيقة")
    return " و ".join(parts)


def _upsert_notification(notification_type, title, message, borrowing=None, reservation=None, member=None):
    queryset = Notification.objects.filter(notification_type=notification_type)
    if borrowing is not None:
        queryset = queryset.filter(borrowing=borrowing)
    elif reservation is not None:
        queryset = queryset.filter(reservation=reservation)
    elif member is not None:
        queryset = queryset.filter(member=member)

    notification = queryset.order_by("-id").first()
    defaults = {
        "title": title,
        "message": message,
        "borrowing": borrowing,
        "reservation": reservation,
        "member": member,
    }

    if notification:
        updates = []
        for key, value in defaults.items():
            if getattr(notification, key) != value:
                setattr(notification, key, value)
                updates.append(key)
        if updates:
            updates.append("updated_at")
            notification.save(update_fields=updates)
        return notification

    return Notification.objects.create(notification_type=notification_type, **defaults)


def create_reservation_created_notification(reservation):
    return _upsert_notification(
        Notification.TYPE_RESERVATION_CREATED,
        "طلب حجز جديد",
        f"قام العضو {reservation.member.name} بطلب حجز الكتاب {reservation.book.title}.",
        reservation=reservation,
        member=reservation.member,
    )


def create_reservation_approved_notification(reservation):
    notification = _upsert_notification(
        Notification.TYPE_RESERVATION_APPROVED,
        "تمت الموافقة على الحجز",
        f"تمت الموافقة على الحجز الخاص بالعضو {reservation.member.name} للكتاب {reservation.book.title}.",
        reservation=reservation,
        member=reservation.member,
    )
    send_member_message(
        member=reservation.member,
        message_type="reservation_approved",
        notification=notification,
        skip_if_notification_sent=True,
    )
    return notification


def sync_overdue_notifications():
    now = timezone.now()
    overdue_borrowings = Borrowing.objects.select_related("member", "book_copy__book").filter(
        return_date__isnull=True,
        due_date__lt=now,
    )

    for borrowing in overdue_borrowings:
        fine_snapshot = calculate_fine_snapshot(borrowing.due_date, reference_time=now)
        delay_text = _format_overdue_duration(fine_snapshot["delay"])
        notification = _upsert_notification(
            Notification.TYPE_OVERDUE,
            "انتهاء مدة الاستعارة",
            f"العضو {borrowing.member.name} تأخر في إعادة الكتاب {borrowing.book_copy.book.title} لمدة {delay_text}.",
            borrowing=borrowing,
            member=borrowing.member,
        )


def sync_due_soon_notifications():
    now = timezone.now()
    reminder_end = now + timezone.timedelta(days=1)
    due_borrowings = Borrowing.objects.select_related("member", "book_copy__book").filter(
        return_date__isnull=True,
        due_date__gt=now,
        due_date__lte=reminder_end,
    )

    active_borrowing_ids = set()
    for borrowing in due_borrowings:
        active_borrowing_ids.add(borrowing.id)
        _upsert_notification(
            Notification.TYPE_DUE_SOON,
            "Borrowing due soon",
            f"Book: {borrowing.book_copy.book.title}\nMember: {borrowing.member.name}\nDue: {borrowing.due_date:%Y-%m-%d %H:%M}",
            borrowing=borrowing,
            member=borrowing.member,
        )

    Notification.objects.filter(notification_type=Notification.TYPE_DUE_SOON).exclude(
        borrowing_id__in=active_borrowing_ids
    ).delete()


def _available_copies_for_book(book):
    usable_copies = BookCopy.objects.filter(book=book, status="new").count()
    active_borrowings = Borrowing.objects.filter(book_copy__book=book, return_date__isnull=True).count()
    return max(usable_copies - active_borrowings, 0)


def notify_reserved_book_available(book):
    available_slots = _available_copies_for_book(book)
    if available_slots <= 0:
        return

    waiting_reservations = list(
        Reservation.objects.select_related("member", "book")
        .filter(book=book, status="approved", cancel_date__isnull=True)
        .order_by("approved_at", "reservation_date")[:available_slots]
    )
    window_start = timezone.now()
    for reservation in waiting_reservations:
        reservation.cancel_date = window_start + get_reservation_duration()
        reservation.save(update_fields=["cancel_date"])
        notification = _upsert_notification(
            Notification.TYPE_RESERVATION_AVAILABLE,
            "كتاب محجوز أصبح متاحًا",
            f"الكتاب {reservation.book.title} أصبح متاحًا الآن للعضو {reservation.member.name}.",
            reservation=reservation,
            member=reservation.member,
        )
        send_member_message(
            member=reservation.member,
            message_type="book_available",
            notification=notification,
            skip_if_notification_sent=True,
        )


def sync_high_risk_members_notifications():
    now = timezone.now()
    thirty_days_ago = now - timezone.timedelta(days=30)

    members_with_stats = Member.objects.annotate(
        current_overdues=Count(
            "borrowing",
            filter=Q(borrowing__return_date__isnull=True, borrowing__due_date__lt=now),
        ),
        recent_delays=Count(
            "borrowing",
            filter=Q(
                borrowing__due_date__gte=thirty_days_ago,
                borrowing__due_date__lt=now,
            )
            & (Q(borrowing__return_date__isnull=True) | Q(borrowing__return_date__gt=F("borrowing__due_date"))),
        ),
    ).filter(Q(current_overdues__gt=2) | Q(recent_delays__gte=2))

    active_member_ids = set()

    for member in members_with_stats:
        active_member_ids.add(member.id)

        delayed_borrowings = Borrowing.objects.filter(member=member, due_date__lt=now).filter(
            Q(return_date__isnull=True) | Q(return_date__gt=F("due_date"))
        )
        total_delays = delayed_borrowings.count()

        total_overdue_seconds = 0
        for borrowing in delayed_borrowings:
            end_date = borrowing.return_date if borrowing.return_date else now
            delay = end_date - borrowing.due_date
            if delay.total_seconds() > 0:
                total_overdue_seconds += delay.total_seconds()

        total_overdue_days = int(total_overdue_seconds // 86400)

        message = (
            f"العضو: {member.name}\n"
            f"عدد التأخيرات: {total_delays}\n"
            f"إجمالي أيام التأخير: {total_overdue_days} يوم\n"
            "تنبيه: يوصى بإرسال إنذار قبل إيقاف العضوية."
        )

        notification = _upsert_notification(
            Notification.TYPE_HIGH_RISK_MEMBER,
            "عضو غير ملتزم - تأخيرات متكررة",
            message,
            member=member,
        )

    Notification.objects.filter(notification_type=Notification.TYPE_HIGH_RISK_MEMBER).exclude(
        member_id__in=active_member_ids
    ).delete()


def sync_pending_fines_notifications():
    members_with_fines = (
        Member.objects.filter(borrowing__fine__paid=False)
        .annotate(unpaid_count=Count("borrowing__fine", filter=Q(borrowing__fine__paid=False), distinct=True))
        .annotate(unpaid_total=Sum("borrowing__fine__amount", filter=Q(borrowing__fine__paid=False)))
        .distinct()
    )

    active_member_ids = set()
    for member in members_with_fines:
        active_member_ids.add(member.id)
        notification = _upsert_notification(
            Notification.TYPE_PENDING_FINE,
            "غرامات غير مدفوعة",
            f"العضو {member.name} لديه {member.unpaid_count} غرامة غير مدفوعة بإجمالي {member.unpaid_total or 0}.",
            member=member,
        )

    Notification.objects.filter(notification_type=Notification.TYPE_PENDING_FINE).exclude(
        member_id__in=active_member_ids
    ).delete()


def sync_suspended_members_notifications():
    suspended_members = Member.objects.filter(is_suspended=True)
    active_member_ids = set()

    for member in suspended_members:
        active_member_ids.add(member.id)
        reason = f" السبب: {member.suspension_reason}." if member.suspension_reason else ""
        notification = _upsert_notification(
            Notification.TYPE_SUSPENDED_MEMBER,
            "عضو موقوف",
            f"العضو {member.name} موقوف عن الاستعارة.{reason}",
            member=member,
        )

    Notification.objects.filter(notification_type=Notification.TYPE_SUSPENDED_MEMBER).exclude(
        member_id__in=active_member_ids
    ).delete()


def notification_target_url(notification, user):
    if notification.notification_type in {
        Notification.TYPE_RESERVATION_CREATED,
        Notification.TYPE_RESERVATION_APPROVED,
        Notification.TYPE_RESERVATION_AVAILABLE,
    }:
        return f"{reverse('dashboard_circulation')}#reservations"

    if notification.notification_type == Notification.TYPE_OVERDUE:
        return f"{reverse('dashboard_reports')}?table=overdue"

    if notification.notification_type == Notification.TYPE_SUSPENDED_MEMBER:
        return f"{reverse('dashboard_circulation')}#manual-borrow"

    if notification.member_id:
        if is_primary_admin(user) or user.is_superuser or getattr(user, "can_manage_members", False):
            return reverse("edit_member", args=[notification.member_id])
        return f"{reverse('member_portal')}?member_id={notification.member_id}"

    return reverse("dashboard_home")


def get_admin_notifications(limit=8):
    sync_overdue_notifications()
    sync_due_soon_notifications()
    sync_high_risk_members_notifications()
    sync_pending_fines_notifications()
    sync_suspended_members_notifications()
    sync_automatic_member_messages()
    return Notification.objects.select_related("member", "borrowing", "reservation").order_by("-updated_at", "-id")[:limit]
