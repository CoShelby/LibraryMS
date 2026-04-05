from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Sum
from django.utils import timezone

from circulations.models import Borrowing, Fine
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


def send_member_message(member, message_type, sent_by=None, notification=None):
    snapshot = _member_status_snapshot(member)
    subject, body = _message_template(message_type, member, snapshot)

    results = {
        "email_sent": False,
        "sms_prepared": False,
        "errors": [],
    }

    if member.email:
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[member.email],
                fail_silently=False,
            )
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

