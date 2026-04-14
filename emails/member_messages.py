from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone

from circulations.models import Borrowing, Fine, Reservation
from circulations.timing import get_reservation_reminder_lead_time
from dashboard.branding import get_library_branding
from libraryms.validation import normalize_yemen_phone

from emails.models import MemberMessageLog
from notifications.models import Notification


NOTIFICATION_MESSAGE_TYPE_MAP = {
    Notification.TYPE_OVERDUE: MemberMessageLog.MESSAGE_OVERDUE,
    Notification.TYPE_RESERVATION_APPROVED: MemberMessageLog.MESSAGE_RESERVATION_APPROVED,
    Notification.TYPE_RESERVATION_AVAILABLE: MemberMessageLog.MESSAGE_BOOK_AVAILABLE,
    Notification.TYPE_PENDING_FINE: MemberMessageLog.MESSAGE_PENDING_FINE,
    Notification.TYPE_HIGH_RISK_MEMBER: MemberMessageLog.MESSAGE_SUSPENSION_WARNING,
    Notification.TYPE_SUSPENDED_MEMBER: MemberMessageLog.MESSAGE_SUSPENSION_WARNING,
}


def message_type_from_notification(notification):
    return NOTIFICATION_MESSAGE_TYPE_MAP.get(notification.notification_type, MemberMessageLog.MESSAGE_GENERAL)


def _member_status_snapshot(member):
    now = timezone.now()
    overdue_count = Borrowing.objects.filter(member=member, return_date__isnull=True, due_date__lt=now).count()
    unpaid_fines = Fine.objects.filter(borrowing__member=member, paid=False)
    unpaid_count = unpaid_fines.count()
    unpaid_total = unpaid_fines.aggregate(total=Sum("amount")).get("total") or 0

    return {
        "overdue_count": overdue_count,
        "unpaid_count": unpaid_count,
        "unpaid_total": unpaid_total,
    }


def _message_template(message_type, member, snapshot):
    if message_type == MemberMessageLog.MESSAGE_OVERDUE:
        subject = "تذكير بإرجاع الكتب المتأخرة"
        body = (
            f"مرحبًا {member.name},\n\n"
            f"لديك {snapshot['overdue_count']} استعارة متأخرة. يرجى مراجعة المكتبة لإرجاع الكتب في أقرب وقت.\n"
            "يمكنك متابعة التفاصيل من بوابة العضو.\n\n"
            "مع تحيات إدارة المكتبة."
        )
    elif message_type == MemberMessageLog.MESSAGE_RESERVATION_APPROVED:
        subject = "تمت الموافقة على طلب الحجز"
        body = (
            f"مرحبًا {member.name},\n\n"
            "تمت الموافقة على طلب الحجز الخاص بك. يرجى الحضور خلال مدة الحجز لاستكمال الاستعارة.\n\n"
            "مع تحيات إدارة المكتبة."
        )
    elif message_type == MemberMessageLog.MESSAGE_BOOK_AVAILABLE:
        subject = "الكتاب المحجوز أصبح متاحًا"
        body = (
            f"مرحبًا {member.name},\n\n"
            "الكتاب الذي قمت بحجزه أصبح متاحًا الآن. يرجى مراجعة المكتبة لاستلامه قبل انتهاء مدة الحجز.\n\n"
            "مع تحيات إدارة المكتبة."
        )
    elif message_type == MemberMessageLog.MESSAGE_PENDING_FINE:
        subject = "تنبيه بوجود غرامات غير مدفوعة"
        body = (
            f"مرحبًا {member.name},\n\n"
            f"لديك {snapshot['unpaid_count']} غرامة غير مدفوعة بإجمالي {snapshot['unpaid_total']}. "
            "يرجى مراجعة المكتبة لتسوية الوضع.\n\n"
            "مع تحيات إدارة المكتبة."
        )
    elif message_type == MemberMessageLog.MESSAGE_SUSPENSION_WARNING:
        subject = "إنذار قبل إيقاف العضوية"
        body = (
            f"مرحبًا {member.name},\n\n"
            "يوجد سجل تأخير/التزامات مالية غير مسددة على حسابك. "
            "يرجى معالجة الوضع فورًا لتجنب إيقاف العضوية ومنع الاستعارة.\n\n"
            "مع تحيات إدارة المكتبة."
        )
    else:
        subject = "إشعار من المكتبة"
        body = (
            f"مرحبًا {member.name},\n\n"
            "هذه رسالة متابعة من إدارة المكتبة.\n\n"
            "مع تحيات إدارة المكتبة."
        )

    return subject, body


def _render_email_html(member, subject, body):
    branding = get_library_branding()
    return render_to_string(
        "emails/member_message.html",
        {
            "member": member,
            "subject": subject,
            "body": body,
            "library_name": getattr(branding, "name", "") or "LibraryMS",
            "library_tagline": getattr(branding, "tagline", "") or "",
        },
    )


def _sent_log_exists(member, message_type, notification=None, sent_after=None):
    queryset = MemberMessageLog.objects.filter(
        member=member,
        message_type=message_type,
        channel=MemberMessageLog.CHANNEL_EMAIL,
        status=MemberMessageLog.STATUS_SENT,
    )
    if notification is not None:
        queryset = queryset.filter(notification=notification)
    if sent_after is not None:
        queryset = queryset.filter(created_at__gte=sent_after)
    return queryset.exists()


def sync_automatic_member_messages(now=None):
    current_time = now or timezone.now()
    reminder_lead_time = get_reservation_reminder_lead_time()
    reminders_sent = 0

    notifications = Notification.objects.select_related("reservation__member").filter(
        notification_type=Notification.TYPE_RESERVATION_APPROVED,
        reservation__status="approved",
        reservation__cancel_date__isnull=False,
        reservation__cancel_date__gt=current_time,
        reservation__cancel_date__lte=current_time + reminder_lead_time,
    )

    for notification in notifications:
        reservation = notification.reservation
        if not reservation or not reservation.member_id:
            continue

        result = send_member_message(
            member=reservation.member,
            message_type=MemberMessageLog.MESSAGE_RESERVATION_APPROVED,
            notification=notification,
            skip_if_sent_after=reservation.cancel_date - reminder_lead_time,
        )
        if result["email_sent"]:
            reminders_sent += 1

    return reminders_sent


def send_member_message(
    member,
    message_type,
    sent_by=None,
    notification=None,
    skip_if_notification_sent=False,
    skip_if_sent_after=None,
):
    snapshot = _member_status_snapshot(member)
    subject, body = _message_template(message_type, member, snapshot)

    results = {
        "email_sent": False,
        "sms_prepared": False,
        "errors": [],
        "skipped": False,
    }

    if skip_if_notification_sent and notification is not None and _sent_log_exists(
        member,
        message_type,
        notification=notification,
    ):
        results["skipped"] = True
        return results

    if skip_if_sent_after is not None and _sent_log_exists(
        member,
        message_type,
        notification=notification,
        sent_after=skip_if_sent_after,
    ):
        results["skipped"] = True
        return results

    if member.email:
        try:
            message = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[member.email],
            )
            message.attach_alternative(_render_email_html(member, subject, body), "text/html")
            message.send(fail_silently=False)
            MemberMessageLog.objects.create(
                member=member,
                notification=notification,
                message_type=message_type,
                channel=MemberMessageLog.CHANNEL_EMAIL,
                recipient=member.email,
                subject=subject,
                body=body,
                status=MemberMessageLog.STATUS_SENT,
                sent_by=sent_by,
            )
            results["email_sent"] = True
        except Exception as exc:
            MemberMessageLog.objects.create(
                member=member,
                notification=notification,
                message_type=message_type,
                channel=MemberMessageLog.CHANNEL_EMAIL,
                recipient=member.email,
                subject=subject,
                body=body,
                status=MemberMessageLog.STATUS_FAILED,
                error_message=str(exc),
                sent_by=sent_by,
            )
            results["errors"].append(str(exc))

    return results

