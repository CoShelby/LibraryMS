from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection, send_mail

from dashboard.system_settings import get_library_system_settings


def get_email_config():
    stored = get_library_system_settings()
    host_user = getattr(stored, "email_host_user", "") if stored else ""
    host_password = getattr(stored, "email_host_password", "") if stored else ""

    if host_user and host_password:
        return {
            "host": stored.email_host or settings.EMAIL_HOST,
            "port": stored.email_port or settings.EMAIL_PORT,
            "username": host_user,
            "password": host_password,
            "use_tls": stored.email_use_tls,
            "use_ssl": False,
            "from_email": stored.default_from_email or host_user,
        }

    return {
        "host": settings.EMAIL_HOST,
        "port": settings.EMAIL_PORT,
        "username": settings.EMAIL_HOST_USER,
        "password": settings.EMAIL_HOST_PASSWORD,
        "use_tls": settings.EMAIL_USE_TLS,
        "use_ssl": getattr(settings, "EMAIL_USE_SSL", False),
        "from_email": settings.DEFAULT_FROM_EMAIL,
    }


def get_configured_email_connection():
    config = get_email_config()
    return get_connection(
        host=config["host"],
        port=config["port"],
        username=config["username"],
        password=config["password"],
        use_tls=config["use_tls"],
        use_ssl=config["use_ssl"],
    )


def send_configured_mail(subject, body, recipients, fail_silently=False):
    config = get_email_config()
    return send_mail(
        subject,
        body,
        config["from_email"],
        recipients,
        fail_silently=fail_silently,
        connection=get_configured_email_connection(),
    )


def configured_email_message(subject, body, recipients):
    config = get_email_config()
    return EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=config["from_email"],
        to=recipients,
        connection=get_configured_email_connection(),
    )
