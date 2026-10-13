from .permissions import is_admin, is_staff_member


def roles(request):
    """Makes `is_staff_member` / `is_admin` available in every template (safe on error pages)."""
    user = getattr(request, "user", None)
    if user is None:
        return {"is_staff_member": False, "is_admin": False}
    return {"is_staff_member": is_staff_member(user), "is_admin": is_admin(user)}
