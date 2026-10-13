"""All ticket business rules live here so the website AND the API behave identically."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Min, Q
from django.utils import timezone

from .models import Issue, IssueActivity, IssueResponse, Profile
from .permissions import is_staff_member

User = get_user_model()
Event = IssueActivity.Event


def eligible_staff():
    """Users who may be assigned tickets."""
    return User.objects.filter(is_active=True).filter(
        Q(profile__role__in=[Profile.Role.STAFF, Profile.Role.ADMIN]) | Q(is_superuser=True)
    ).order_by("first_name", "username").distinct()


def display_name(user):
    return (user.get_full_name() or user.get_username()) if user else "System"


def log(issue, event, description, actor):
    return IssueActivity.objects.create(issue=issue, event_type=event, description=description, actor=actor)


def _ensure_open_for_changes(issue):
    if issue.is_closed:
        raise ValidationError("This issue is closed and can no longer be changed.")


@transaction.atomic
def create_issue(student, *, title, description, category, priority, location=""):
    issue = Issue.objects.create(student=student, title=title, description=description,
                                 category=category, priority=priority, location=location)
    log(issue, Event.SUBMITTED, f"Issue submitted by {display_name(student)}.", student)
    return issue


@transaction.atomic
def assign_issue(issue, assignee, actor):
    if not is_staff_member(actor):
        raise PermissionDenied
    _ensure_open_for_changes(issue)
    if assignee is not None and not eligible_staff().filter(pk=assignee.pk).exists():
        raise ValidationError("The selected user is not an eligible staff member.")
    if issue.assigned_to_id == (assignee.pk if assignee else None):
        raise ValidationError("The issue is already assigned to that person.")
    issue.assigned_to = assignee
    issue.save(update_fields=["assigned_to", "updated_at"])
    text = f"Assigned to {display_name(assignee)}." if assignee else "Assignment removed."
    log(issue, Event.ASSIGNED, text, actor)
    return issue


@transaction.atomic
def change_priority(issue, priority, actor):
    if not is_staff_member(actor):
        raise PermissionDenied
    _ensure_open_for_changes(issue)
    if priority not in Issue.Priority.values:
        raise ValidationError("Invalid priority.")
    if priority == issue.priority:
        raise ValidationError("The issue already has that priority.")
    old = issue.get_priority_display()
    issue.priority = priority
    issue.save(update_fields=["priority", "updated_at"])
    log(issue, Event.PRIORITY, f"Priority changed from {old} to {issue.get_priority_display()}.", actor)
    return issue


@transaction.atomic
def change_status(issue, new_status, actor):
    if not is_staff_member(actor):
        raise PermissionDenied
    if new_status not in Issue.Status.values:
        raise ValidationError("Invalid status.")
    if new_status == issue.status:
        raise ValidationError("The issue already has that status.")
    if new_status not in Issue.TRANSITIONS[issue.status]:
        raise ValidationError(
            f"You cannot move an issue from {issue.get_status_display()} to "
            f"{Issue.Status(new_status).label}.")
    old = issue.status
    issue.status = new_status
    if new_status in (Issue.Status.RESOLVED, Issue.Status.CLOSED):
        issue.resolved_at = issue.resolved_at or timezone.now()
    else:  # reopened / in progress
        issue.resolved_at = None
    issue.save(update_fields=["status", "resolved_at", "updated_at"])

    if new_status == Issue.Status.RESOLVED:
        event, text = Event.RESOLVED, "Issue marked as resolved."
    elif new_status == Issue.Status.CLOSED:
        event, text = Event.CLOSED, "Issue closed."
    elif old == Issue.Status.RESOLVED:
        event, text = Event.REOPENED, "Issue reopened and moved back to In Progress."
    else:
        event, text = Event.STARTED, "Work started on this issue."
    log(issue, event, text, actor)
    return issue


@transaction.atomic
def add_response(issue, staff_user, message):
    if not is_staff_member(staff_user):
        raise PermissionDenied  # students can never post as staff
    _ensure_open_for_changes(issue)
    message = (message or "").strip()
    if len(message) < 2 or len(message) > 2000:
        raise ValidationError("A response must be between 2 and 2000 characters.")
    response = IssueResponse.objects.create(issue=issue, staff=staff_user, message=message)
    issue.save(update_fields=["updated_at"])
    log(issue, Event.RESPONSE, f"{display_name(staff_user)} replied.", staff_user)
    return response


# ---------------------------------------------------------------- filtering / stats
def filter_issues(qs, params):
    """Database-backed search + filters shared by website and API."""
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(ticket_id__icontains=q) | Q(description__icontains=q))
    status = params.get("status")
    if status == "done":  # Resolved + Closed
        qs = qs.filter(status__in=[Issue.Status.RESOLVED, Issue.Status.CLOSED])
    elif status in Issue.Status.values:
        qs = qs.filter(status=status)
    if params.get("category") in Issue.Category.values:
        qs = qs.filter(category=params["category"])
    if params.get("priority") in Issue.Priority.values:
        qs = qs.filter(priority=params["priority"])
    assigned = params.get("assigned")
    if assigned == "unassigned":
        qs = qs.filter(assigned_to__isnull=True)
    elif assigned and str(assigned).isdigit():
        qs = qs.filter(assigned_to_id=int(assigned))
    return qs


def issue_counts(qs):
    """Total / open / in progress / resolved (Resolved + Closed).

    resolution_rate = (resolved + closed) / total * 100, or None when there are no issues.
    """
    d = qs.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status=Issue.Status.OPEN)),
        in_progress=Count("id", filter=Q(status=Issue.Status.IN_PROGRESS)),
        resolved=Count("id", filter=Q(status__in=[Issue.Status.RESOLVED, Issue.Status.CLOSED])),
    )
    d["resolution_rate"] = round(d["resolved"] * 100 / d["total"], 1) if d["total"] else None
    return d


def average_first_response(qs):
    """Mean of (first staff response time - ticket creation time) over tickets that have a response."""
    rows = qs.annotate(first=Min("responses__created_at")).filter(first__isnull=False) \
        .values_list("created_at", "first")
    deltas = [first - created for created, first in rows]
    return sum(deltas, timedelta()) / len(deltas) if deltas else None


def average_resolution_time(qs):
    """Mean of (resolved_at - created_at) over tickets that have been resolved."""
    rows = qs.filter(resolved_at__isnull=False).values_list("created_at", "resolved_at")
    deltas = [done - created for created, done in rows]
    return sum(deltas, timedelta()) / len(deltas) if deltas else None


def week_start():
    now = timezone.localtime()
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def breakdown(qs, field, choices):
    """[(label, count, percent)] including zero rows, for the CSS bar charts."""
    counts = dict(qs.order_by().values_list(field).annotate(n=Count("id")))
    total = sum(counts.values()) or 1
    return [(label, counts.get(value, 0), round(counts.get(value, 0) * 100 / total)) for value, label in choices]
