from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def is_library_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.is_staff or getattr(user, "is_admin", False)
    )


def has_admin_capability(user, capability):
    if user.is_superuser:
        return True
    return bool(getattr(user, capability, False))


def admin_required(view_func):
    @login_required(login_url="login")
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not is_library_admin(request.user):
            raise PermissionDenied("Supervisor access required.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def admin_capability_required(capability):
    def decorator(view_func):
        @login_required(login_url="login")
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not is_library_admin(request.user):
                raise PermissionDenied("Supervisor access required.")
            if not has_admin_capability(request.user, capability):
                raise PermissionDenied("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator

