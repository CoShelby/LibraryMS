from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from dashboard.system_settings import configured_positive_int


def is_demo_mode():
    return bool(getattr(settings, "LIBRARY_DEMO_MODE", False))


def get_reservation_days():
    return configured_positive_int(
        "reservation_days",
        getattr(settings, "LIBRARY_RESERVATION_DAYS", 2),
    )


def get_borrow_days():
    return configured_positive_int(
        "borrow_days",
        getattr(settings, "LIBRARY_BORROW_DAYS", 3),
    )


def get_reservation_duration():
    return timedelta(minutes=2) if is_demo_mode() else timedelta(days=get_reservation_days())


def get_reservation_reminder_lead_time():
    return timedelta(minutes=1) if is_demo_mode() else timedelta(days=1)


def get_borrow_duration():
    return timedelta(minutes=3) if is_demo_mode() else timedelta(days=get_borrow_days())


def get_fine_grace_period():
    return timedelta(minutes=1) if is_demo_mode() else timedelta()


def get_fine_unit_duration():
    return timedelta(minutes=1) if is_demo_mode() else timedelta(days=1)


def get_fine_amount_per_unit():
    return configured_positive_int(
        "fine_amount_per_unit",
        getattr(settings, "LIBRARY_FINE_PER_UNIT", 1000),
    )


def fine_unit_label(count=1):
    if is_demo_mode():
        return "دقيقة" if count == 1 else "دقائق"
    return "يوم" if count == 1 else "أيام"


def describe_reservation_duration():
    return "دقيقتين" if is_demo_mode() else f"{get_reservation_days()} يوم"


def describe_borrow_duration():
    return "3 دقائق" if is_demo_mode() else f"{get_borrow_days()} يوم"


def overdue_timedelta(due_date, reference_time=None):
    now = reference_time or timezone.now()
    return max(now - due_date, timedelta())


def fine_units_from_delay(delay):
    grace_period = get_fine_grace_period()
    if delay <= grace_period:
        return 0

    chargeable_delay = delay - grace_period
    unit_duration = get_fine_unit_duration()
    return max(int(chargeable_delay // unit_duration), 1)


def calculate_fine_snapshot(due_date, reference_time=None):
    delay = overdue_timedelta(due_date, reference_time=reference_time)
    units = fine_units_from_delay(delay)
    amount = units * get_fine_amount_per_unit()
    return {
        "delay": delay,
        "units": units,
        "amount": amount,
        "is_overdue": delay > timedelta(),
        "has_fine": units > 0,
    }
