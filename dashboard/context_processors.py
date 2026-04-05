from accounts.services import is_library_admin

from .branding import get_library_branding
from notifications.models import Notification
from .notifications import get_admin_notifications


def admin_notifications(request):
    branding = get_library_branding()

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False) or not is_library_admin(user):
        return {
            "admin_notifications": [],
            "admin_notification_unread_count": 0,
            "admin_can_manage_accounts": False,
            "library_branding": branding,
        }

    return {
        "admin_notifications": get_admin_notifications(),
        "admin_notification_unread_count": Notification.objects.filter(is_read=False).count(),
        "admin_can_manage_accounts": user.is_superuser or user.can_manage_admins or user.created_admins.filter(is_staff=True, is_superuser=False).exists(),
        "library_branding": branding,
    }

