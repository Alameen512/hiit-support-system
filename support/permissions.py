"""Role checks used by BOTH the website views and the REST API (server-side enforcement)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from rest_framework.permissions import BasePermission


def _role(user):
    profile = getattr(user, "profile", None)  # missing profile -> None
    return profile.role if profile else None


def is_admin(user):
    return bool(user.is_authenticated and (user.is_superuser or _role(user) == "admin"))


def is_staff_member(user):
    """True for staff and administrators (anyone allowed to manage tickets)."""
    return bool(user.is_authenticated and (user.is_superuser or _role(user) in ("staff", "admin")))


def staff_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not is_staff_member(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def student_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if is_staff_member(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def rate_limit(key, limit=10, window=60):
    """Tiny POST rate limiter for public endpoints (login/register).

    Uses Django's cache. The default local-memory cache is per serverless instance,
    so it is a basic brake against guessing, not a global limit (see README).
    """
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "POST":
                ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() \
                    or request.META.get("REMOTE_ADDR", "unknown")
                cache_key = f"rl:{key}:{ip}"
                cache.add(cache_key, 0, window)
                try:
                    count = cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, window)
                    count = 1
                if count > limit:
                    return HttpResponse("Too many attempts. Please wait a minute and try again.", status=429)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


class IsStaffMember(BasePermission):
    def has_permission(self, request, view):
        return is_staff_member(request.user)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user)
