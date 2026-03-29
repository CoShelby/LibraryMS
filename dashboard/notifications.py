from django.utils import timezone

from books.models import BookCopy
from circulations.models import Borrowing, Reservation
from circulations.timing import calculate_fine_snapshot

from .models import Notification


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


def _upsert_notification(notification_type, title, message, borrowing=None, reservation=None):
    queryset = Notification.objects.filter(notification_type=notification_type)
    if borrowing is not None:
        queryset = queryset.filter(borrowing=borrowing)
    elif reservation is not None:
        queryset = queryset.filter(reservation=reservation)
    notification = queryset.order_by("-id").first()

    if notification:
        if notification.title != title or notification.message != message:
            notification.title = title
            notification.message = message
            notification.save(update_fields=["title", "message", "updated_at"])
        return notification

    return Notification.objects.create(
        notification_type=notification_type,
        title=title,
        message=message,
        borrowing=borrowing,
        reservation=reservation,
    )


def create_reservation_created_notification(reservation):
    return _upsert_notification(
        Notification.TYPE_RESERVATION_CREATED,
        "طلب حجز جديد",
        f"قام العضو {reservation.member.name} بطلب حجز الكتاب {reservation.book.title}.",
        reservation=reservation,
    )


def sync_overdue_notifications():
    now = timezone.now()
    overdue_borrowings = Borrowing.objects.select_related("member", "book_copy__book").filter(
        return_date__isnull=True,
        due_date__lt=now,
    )

    for borrowing in overdue_borrowings:
        fine_snapshot = calculate_fine_snapshot(borrowing.due_date, reference_time=now)
        delay_text = _format_overdue_duration(fine_snapshot["delay"])
        _upsert_notification(
            Notification.TYPE_OVERDUE,
            "انتهاء مدة الاستعارة",
            f"العضو {borrowing.member.name} تأخر في إعادة الكتاب {borrowing.book_copy.book.title} لمدة {delay_text}.",
            borrowing=borrowing,
        )


def _available_copies_for_book(book):
    usable_copies = BookCopy.objects.filter(book=book, status="new").count()
    active_borrowings = Borrowing.objects.filter(book_copy__book=book, return_date__isnull=True).count()
    approved_reservations = Reservation.objects.filter(book=book, status="approved").count()
    return max(usable_copies - active_borrowings - approved_reservations, 0)


def notify_reserved_book_available(book):
    available_slots = _available_copies_for_book(book)
    if available_slots <= 0:
        return

    pending_reservations = list(
        Reservation.objects.select_related("member", "book")
        .filter(book=book, status="pending")
        .order_by("reservation_date")[:available_slots]
    )
    for reservation in pending_reservations:
        _upsert_notification(
            Notification.TYPE_RESERVATION_AVAILABLE,
            "كتاب محجوز أصبح متاحًا",
            f"الكتاب {reservation.book.title} أصبح متاحًا الآن للعضو {reservation.member.name}.",
            reservation=reservation,
        )


def sync_high_risk_members_notifications():
    now = timezone.now()
    thirty_days_ago = now - timezone.timedelta(days=30)
    from django.db.models import Count, Q, F
    from members.models import Member
    
    members_with_stats = Member.objects.annotate(
        current_overdues=Count(
            'borrowing',
            filter=Q(borrowing__return_date__isnull=True, borrowing__due_date__lt=now)
        ),
        recent_delays=Count(
            'borrowing',
            filter=Q(
                borrowing__due_date__gte=thirty_days_ago,
                borrowing__due_date__lt=now,
            ) & (Q(borrowing__return_date__isnull=True) | Q(borrowing__return_date__gt=F('borrowing__due_date')))
        )
    ).filter(
        Q(current_overdues__gt=2) | Q(recent_delays__gte=2)
    )

    current_high_risk_member_ids = set()

    for member in members_with_stats:
        current_high_risk_member_ids.add(member.id)
        
        all_delays = Borrowing.objects.filter(
            member=member,
            due_date__lt=now
        ).filter(
            Q(return_date__isnull=True) | Q(return_date__gt=F('due_date'))
        )
        total_delays = all_delays.count()
        
        total_overdue_seconds = 0
        for b in all_delays:
            end_date = b.return_date if b.return_date else now
            delay = end_date - b.due_date
            if delay.total_seconds() > 0:
                total_overdue_seconds += delay.total_seconds()
        
        total_overdue_days = int(total_overdue_seconds // 86400)
        
        message = (f"العضو: {member.name}\n"
                   f"عدد التأخيرات: {total_delays}\n"
                   f"إجمالي أيام التأخير: {total_overdue_days} يوم\n"
                   f"معرف العضو: {member.id}")
        
        existing = Notification.objects.filter(
            notification_type=Notification.TYPE_HIGH_RISK_MEMBER,
            message__contains=f"معرف العضو: {member.id}"
        ).first()
        
        if existing:
            if existing.message != message:
                existing.message = message
                existing.save(update_fields=["message", "updated_at"])
        else:
            Notification.objects.create(
                notification_type=Notification.TYPE_HIGH_RISK_MEMBER,
                title="عضو غير ملتزم - تأخيرات متكررة",
                message=message
            )

    all_high_risk = Notification.objects.filter(notification_type=Notification.TYPE_HIGH_RISK_MEMBER)
    for notif in all_high_risk:
        is_current = False
        for m_id in current_high_risk_member_ids:
            if f"معرف العضو: {m_id}" in notif.message:
                is_current = True
                break
        if not is_current:
            notif.delete()


def get_admin_notifications(limit=8):
    sync_overdue_notifications()
    sync_high_risk_members_notifications()
    return Notification.objects.order_by("-updated_at", "-id")[:limit]