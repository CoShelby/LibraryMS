from rest_framework.permissions import BasePermission

from accounts.services import is_primary_admin


class CanAccessMemberFinanceAPI(BasePermission):
    message = "You do not have permission to access member finance data."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                is_primary_admin(user)
                or user.is_superuser
                or getattr(user, "can_manage_members", False)
                or getattr(user, "can_manage_circulation", False)
            )
        )

class CanSubmitExternalFinePayments(BasePermission):
    message = "You do not have permission to submit fine payments."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (is_primary_admin(user) or user.is_superuser or getattr(user, "can_manage_circulation", False))
        )
