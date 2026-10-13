from django import template

register = template.Library()

CATEGORY_ICONS = {
    "technical": "bi-pc-display", "academic": "bi-mortarboard", "administrative": "bi-briefcase",
    "course_registration": "bi-journal-check", "laboratory": "bi-eyedropper",
    "certificate": "bi-award", "payment": "bi-credit-card", "other": "bi-three-dots",
}
EVENT_ICONS = {
    "submitted": "bi-send", "assigned": "bi-person-check", "priority": "bi-flag",
    "started": "bi-play-circle", "response": "bi-chat-dots", "resolved": "bi-check-circle",
    "closed": "bi-lock", "reopened": "bi-arrow-counterclockwise",
}


@register.filter
def category_icon(value):
    return CATEGORY_ICONS.get(value, "bi-three-dots")


@register.filter
def event_icon(value):
    return EVENT_ICONS.get(value, "bi-circle")


@register.filter
def duration(td):
    """timedelta -> '4h 32m' / '2d 3h'; None -> 'N/A'."""
    if td is None:
        return "N/A"
    minutes = int(td.total_seconds() // 60)
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


@register.filter
def percent(value):
    return "N/A" if value is None else f"{value}%"


@register.filter
def display_name(user):
    return (user.get_full_name() or user.get_username()) if user else "Unassigned"


@register.filter
def initials(user):
    name = (user.get_full_name() or user.get_username()) if user else "?"
    parts = name.split()
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()
