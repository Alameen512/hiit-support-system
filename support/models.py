import secrets

from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Profile(models.Model):
    """Role + contact details for a user. Public registration only ever creates students."""

    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        STAFF = "staff", "Staff"
        ADMIN = "admin", "Administrator"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=20, blank=True)
    matric_number = models.CharField(max_length=30, blank=True)
    department = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # An "Administrator" must be able to open Django Admin, so keep the flags in step.
        # Roles can only be changed in Django Admin by a superuser.
        if self.role == self.Role.ADMIN and not (self.user.is_staff and self.user.is_superuser):
            self.user.is_staff = True
            self.user.is_superuser = True
            self.user.save(update_fields=["is_staff", "is_superuser"])
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"


class Issue(models.Model):
    class Category(models.TextChoices):
        TECHNICAL = "technical", "Technical"
        ACADEMIC = "academic", "Academic"
        ADMINISTRATIVE = "administrative", "Administrative"
        COURSE = "course_registration", "Course/Registration"
        LABORATORY = "laboratory", "Laboratory"
        CERTIFICATE = "certificate", "Certificate"
        PAYMENT = "payment", "Payment"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    # Allowed status moves: Open -> In Progress -> Resolved -> Closed (resolved may be reopened).
    TRANSITIONS = {
        "open": ["in_progress", "closed"],
        "in_progress": ["resolved", "closed"],
        "resolved": ["closed", "in_progress"],
        "closed": [],
    }

    ticket_id = models.CharField(max_length=20, unique=True, editable=False)
    student = models.ForeignKey(User, on_delete=models.PROTECT, related_name="issues")
    title = models.CharField(max_length=150)
    description = models.TextField(max_length=3000)
    category = models.CharField(max_length=30, choices=Category.choices)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)
    location = models.CharField(max_length=100, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="assigned_issues")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="issue_status_idx"),
            models.Index(fields=["category"], name="issue_category_idx"),
            models.Index(fields=["created_at"], name="issue_created_idx"),
        ]

    def __str__(self):
        return f"{self.ticket_id}: {self.title}"

    @staticmethod
    def _new_ticket_id():
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no confusing 0/O/1/I
        return "HIT-" + "".join(secrets.choice(alphabet) for _ in range(6))

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            # Retry on the (very unlikely) collision; the unique constraint is the final guard.
            while True:
                candidate = self._new_ticket_id()
                if not Issue.objects.filter(ticket_id=candidate).exists():
                    self.ticket_id = candidate
                    break
        super().save(*args, **kwargs)

    @property
    def allowed_next_statuses(self):
        return [(s, self.Status(s).label) for s in self.TRANSITIONS[self.status]]

    @property
    def is_closed(self):
        return self.status == self.Status.CLOSED


class IssueResponse(models.Model):
    """A message from a staff member to the student on a ticket."""

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="responses")
    staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="issue_responses")
    message = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Response on {self.issue.ticket_id}"


class IssueActivity(models.Model):
    """Append-only audit trail. Written by support/services.py, never by users directly."""

    class Event(models.TextChoices):
        SUBMITTED = "submitted", "Issue submitted"
        ASSIGNED = "assigned", "Assignment changed"
        PRIORITY = "priority", "Priority changed"
        STARTED = "started", "Work started"
        RESPONSE = "response", "Staff response added"
        RESOLVED = "resolved", "Issue resolved"
        CLOSED = "closed", "Issue closed"
        REOPENED = "reopened", "Issue reopened"

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="activities")
    event_type = models.CharField(max_length=15, choices=Event.choices)
    description = models.CharField(max_length=255)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="issue_activities")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "issue activities"

    def __str__(self):
        return f"{self.issue.ticket_id} - {self.event_type}"
