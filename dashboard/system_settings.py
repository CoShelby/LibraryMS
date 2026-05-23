from django.apps import apps
from django.conf import settings
from django.db import OperationalError, ProgrammingError


def get_library_system_settings():
    if not apps.ready:
        return None

    try:
        settings_model = apps.get_model("dashboard", "LibrarySystemSettings")
        return settings_model.objects.order_by("id").first()
    except (LookupError, OperationalError, ProgrammingError):
        return None


def get_or_create_library_system_settings():
    settings_model = apps.get_model("dashboard", "LibrarySystemSettings")
    obj = settings_model.objects.order_by("id").first()
    if obj:
        return obj
    return settings_model.objects.create(
        fine_amount_per_unit=getattr(settings, "LIBRARY_FINE_PER_UNIT", 1000),
        reservation_days=getattr(settings, "LIBRARY_RESERVATION_DAYS", 2),
        borrow_days=getattr(settings, "LIBRARY_BORROW_DAYS", 3),
        email_host=getattr(settings, "EMAIL_HOST", "smtp.gmail.com"),
        email_port=getattr(settings, "EMAIL_PORT", 587),
        email_use_tls=getattr(settings, "EMAIL_USE_TLS", True),
        email_host_user=getattr(settings, "EMAIL_HOST_USER", "") or "",
        email_host_password=getattr(settings, "EMAIL_HOST_PASSWORD", "") or "",
        default_from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "") or "",
    )


def configured_positive_int(field_name, fallback):
    obj = get_library_system_settings()
    value = getattr(obj, field_name, None) if obj else None
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = int(fallback)
    return max(value, 1)
