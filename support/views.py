from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import (AssignForm, IssueForm, PriorityForm, ProfileForm, RegisterForm,
                    ResponseForm, StatusForm)
from .models import Issue, Profile
from .permissions import is_staff_member, rate_limit, staff_required, student_required

User = get_user_model()


# ------------------------------------------------------------------ public pages
def landing(request):
    return render(request, "landing.html")


INFO_PAGES = {
    "about": ("About HIIT Plc", "HIIT Plc is an IT training institute. HIIT Support is the platform "
              "where students report problems and staff resolve them transparently."),
    "training": ("Training Programs", "HIIT offers practical IT training programmes. Ask the front desk or "
                 "raise an Administrative ticket for programme and schedule enquiries."),
    "contact": ("Contact", "Visit the HIIT front desk during working hours, or submit a ticket from your "
                "dashboard so that the right staff member can respond in writing."),
    "help": ("Help Center", "Sign in, click Submit New Issue, choose the closest category and describe the "
             "problem. You can follow progress and read staff replies on the ticket page at any time."),
    "faq": ("FAQs", "How long do replies take? It depends on priority and staff availability. Can I edit a "
            "ticket? Add detail by submitting a follow-up ticket; staff replies appear on your ticket."),
    "privacy": ("Privacy", "Your tickets are visible only to you and authorised HIIT staff."),
}


def info_page(request, slug):
    if slug not in INFO_PAGES:
        return error_404(request, None)
    title, body = INFO_PAGES[slug]
    return render(request, "info/page.html", {"title": title, "body": body})


# ------------------------------------------------------------------ auth
@rate_limit("register", limit=10, window=300)
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to HIIT Support! Your account is ready.")
            return redirect("dashboard")
        messages.error(request, "Please fix the errors below.")
    return render(request, "registration/register.html", {"form": form})


class HiitLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def form_invalid(self, form):
        messages.error(request=self.request, message="Incorrect username or password.")
        return super().form_invalid(form)


login_view = rate_limit("login", limit=10, window=300)(HiitLoginView.as_view())


class HiitPasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("settings")

    def form_valid(self, form):
        messages.success(self.request, "Your password was changed.")
        return super().form_valid(form)


@login_required
def dashboard(request):
    if is_staff_member(request.user):
        return redirect("staff_dashboard")
    mine = Issue.objects.filter(student=request.user)
    ctx = {
        "nav": "dashboard",
        "counts": services.issue_counts(mine),
        "recent": mine.select_related("assigned_to")[:5],
    }
    return render(request, "student/dashboard.html", ctx)


# ------------------------------------------------------------------ student issues
def _paginate(request, qs, per_page=10):
    return Paginator(qs, per_page).get_page(request.GET.get("page"))


def _filter_context(request, page):
    query = request.GET.copy()
    query.pop("page", None)
    return {"page": page, "querystring": query.urlencode(),
            "categories": Issue.Category.choices, "statuses": Issue.Status.choices,
            "priorities": Issue.Priority.choices, "params": request.GET}


@student_required
def my_issues(request):
    qs = Issue.objects.filter(student=request.user).select_related("assigned_to")  # own tickets only
    qs = services.filter_issues(qs, request.GET)
    ctx = {"nav": "issues", **_filter_context(request, _paginate(request, qs))}
    return render(request, "student/issue_list.html", ctx)


@student_required
def issue_create(request):
    form = IssueForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            # Ownership comes from the logged-in session, never from submitted data.
            issue = services.create_issue(request.user, **form.cleaned_data)
            messages.success(request, f"Issue submitted. Your ticket ID is {issue.ticket_id}.")
            return redirect("issue_detail", ticket_id=issue.ticket_id)
        messages.error(request, "We could not submit your issue. Please check the form.")
    return render(request, "student/issue_form.html", {"form": form, "nav": "new"})


@login_required
def issue_detail(request, ticket_id):
    issue = get_object_or_404(Issue.objects.select_related("student", "assigned_to"), ticket_id=ticket_id)
    staff = is_staff_member(request.user)
    if not staff and issue.student_id != request.user.id:
        # 404 (not 403) so students cannot discover other students' ticket IDs.
        return error_404(request, None)
    ctx = {
        "issue": issue, "nav": "issues" if not staff else "all",
        "responses": issue.responses.select_related("staff"),
        "activities": issue.activities.select_related("actor"),
    }
    if staff:
        ctx.update(
            assign_form=AssignForm(initial={"assignee": issue.assigned_to_id}),
            response_form=ResponseForm(),
            priorities=Issue.Priority.choices,
            next_statuses=issue.allowed_next_statuses,
        )
    return render(request, "issue_detail.html", ctx)


@staff_required
@require_POST
def issue_action(request, ticket_id, action):
    """One endpoint for staff actions: assign, status, priority, respond."""
    issue = get_object_or_404(Issue, ticket_id=ticket_id)
    try:
        if action == "assign":
            form = AssignForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Choose a valid staff member.")
            services.assign_issue(issue, form.cleaned_data["assignee"], request.user)
            messages.success(request, "Assignment updated.")
        elif action == "status":
            form = StatusForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Choose a valid status.")
            services.change_status(issue, form.cleaned_data["status"], request.user)
            messages.success(request, f"Status changed to {issue.get_status_display()}.")
        elif action == "priority":
            form = PriorityForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Choose a valid priority.")
            services.change_priority(issue, form.cleaned_data["priority"], request.user)
            messages.success(request, "Priority updated.")
        elif action == "respond":
            form = ResponseForm(request.POST)
            if not form.is_valid():
                raise ValidationError("Write a response between 2 and 2000 characters.")
            services.add_response(issue, request.user, form.cleaned_data["message"])
            messages.success(request, "Response sent to the student.")
        else:
            return error_404(request, None)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("issue_detail", ticket_id=issue.ticket_id)


# ------------------------------------------------------------------ staff area
@staff_required
def staff_dashboard(request):
    all_issues = Issue.objects.all()
    counts = services.issue_counts(all_issues)
    ctx = {
        "nav": "dashboard",
        "counts": counts,
        "students_total": Profile.objects.filter(role=Profile.Role.STUDENT, user__is_active=True).count(),
        "staff_total": services.eligible_staff().count(),
        "this_week": all_issues.filter(created_at__gte=services.week_start()).count(),
        "avg_response": services.average_first_response(all_issues),
        "recent": all_issues.select_related("student", "assigned_to")[:6],
        "by_category": services.breakdown(all_issues, "category", Issue.Category.choices),
        "by_status": services.breakdown(all_issues, "status", Issue.Status.choices),
    }
    return render(request, "staff/dashboard.html", ctx)


@staff_required
def staff_issues(request):
    qs = Issue.objects.select_related("student", "assigned_to")
    qs = services.filter_issues(qs, request.GET)
    status = request.GET.get("status", "")
    nav = {"open": "open", "in_progress": "progress", "done": "resolved"}.get(status, "all")
    ctx = {"nav": nav, "staff_members": services.eligible_staff(),
           **_filter_context(request, _paginate(request, qs))}
    return render(request, "staff/issue_list.html", ctx)


@staff_required
def staff_students(request):
    qs = User.objects.filter(profile__role=Profile.Role.STUDENT).select_related("profile").annotate(
        issue_total=Count("issues"),
        issue_open=Count("issues", filter=Q(issues__status__in=["open", "in_progress"])))
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
                       | Q(email__icontains=q) | Q(profile__matric_number__icontains=q))
    ctx = {"nav": "students", "page": _paginate(request, qs.order_by("first_name", "username")),
           "params": request.GET}
    return render(request, "staff/students.html", ctx)


@staff_required
def staff_members(request):
    qs = services.eligible_staff().select_related("profile").annotate(
        assigned_total=Count("assigned_issues", distinct=True),
        assigned_open=Count("assigned_issues", filter=Q(assigned_issues__status__in=["open", "in_progress"]),
                            distinct=True))
    return render(request, "staff/staff_list.html", {"nav": "staff", "members": qs})


@staff_required
def reports(request):
    qs = Issue.objects.all()
    per_day = dict(qs.filter(created_at__date__gte=timezone.localdate() - timedelta(days=6))
                   .order_by().annotate(day=TruncDate("created_at")).values_list("day").annotate(n=Count("id")))
    days = []
    for i in range(6, -1, -1):
        d = timezone.localdate() - timedelta(days=i)
        days.append((d, per_day.get(d, 0)))
    peak = max([n for _, n in days] + [1])
    ctx = {
        "nav": "reports", "counts": services.issue_counts(qs),
        "avg_response": services.average_first_response(qs),
        "avg_resolution": services.average_resolution_time(qs),
        "by_category": services.breakdown(qs, "category", Issue.Category.choices),
        "by_status": services.breakdown(qs, "status", Issue.Status.choices),
        "by_priority": services.breakdown(qs, "priority", Issue.Priority.choices),
        "days": [(d, n, round(n * 100 / peak)) for d, n in days],
    }
    return render(request, "staff/reports.html", ctx)


# ------------------------------------------------------------------ settings
@login_required
def settings_view(request):
    form = ProfileForm(request.POST or None, instance=request.user.profile, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("settings")
        messages.error(request, "Please fix the errors below.")
    return render(request, "settings.html", {"form": form, "nav": "settings"})


# ------------------------------------------------------------------ error pages
def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
