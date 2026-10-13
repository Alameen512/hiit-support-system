"""Run with:  DEBUG=True python manage.py test   (Windows PowerShell: $env:DEBUG="True")"""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from . import services
from .models import Issue, IssueActivity, Profile

User = get_user_model()
PW = "Str0ng-pass-for-tests"


def make_user(username, role="student", **extra):
    user = User.objects.create_user(username=username, password=PW, email=f"{username}@example.com", **extra)
    Profile.objects.filter(user=user).update(role=role)
    return User.objects.get(pk=user.pk)


class Base(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # reset rate-limit counters between tests
        self.student = make_user("alice", first_name="Alice")
        self.other = make_user("bob")
        self.staff = make_user("sam", "staff", first_name="Sam")
        self.staff2 = make_user("sue", "staff")
        self.issue_data = dict(title="Lab PC broken", description="The PC in lab 2 will not boot at all.",
                               category="laboratory", priority="high")

    def new_issue(self, student=None, **kw):
        return services.create_issue(student or self.student, **{**self.issue_data, **kw})


class AuthTests(Base):
    def reg(self, **kw):
        data = {"first_name": "New", "last_name": "Student", "username": "newbie", "email": "new@example.com",
                "password1": PW, "password2": PW, **kw}
        return self.client.post(reverse("register"), data)

    def test_registration_creates_student_only(self):
        r = self.reg(role="admin", is_staff="on", is_superuser="on")  # extra fields must be ignored
        self.assertRedirects(r, reverse("dashboard"), fetch_redirect_response=False)
        u = User.objects.get(username="newbie")
        self.assertEqual(u.profile.role, "student")
        self.assertFalse(u.is_staff or u.is_superuser)

    def test_registration_rejects_duplicate_email(self):
        self.reg()
        self.client.logout()
        r = self.reg(username="other")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="other").exists())

    def test_login_and_logout(self):
        r = self.client.post(reverse("login"), {"username": "alice", "password": PW})
        self.assertEqual(r.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bad_login(self):
        r = self.client.post(reverse("login"), {"username": "alice", "password": "wrong"})
        self.assertEqual(r.status_code, 200)

    def test_profile_form_cannot_change_role(self):
        self.client.login(username="alice", password=PW)
        self.client.post(reverse("settings"), {"first_name": "A", "last_name": "B", "email": "a@x.com",
                                               "phone": "1", "role": "admin"})
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.role, "student")


class IssueTests(Base):
    def test_submission_via_web(self):
        self.client.login(username="alice", password=PW)
        r = self.client.post(reverse("issue_create"), {**self.issue_data, "location": "Lab 2", "student": self.other.pk})
        issue = Issue.objects.get()
        self.assertRedirects(r, reverse("issue_detail", args=[issue.ticket_id]))
        self.assertEqual(issue.student, self.student)  # posted "student" field is ignored
        self.assertEqual(issue.status, "open")
        self.assertTrue(issue.ticket_id.startswith("HIT-"))
        self.assertEqual(issue.activities.first().event_type, "submitted")

    def test_validation(self):
        self.client.login(username="alice", password=PW)
        r = self.client.post(reverse("issue_create"), {**self.issue_data, "title": "", "description": "short"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Issue.objects.count(), 0)
        r = self.client.post(reverse("issue_create"), {**self.issue_data, "description": "x" * 3001})
        self.assertEqual(Issue.objects.count(), 0)

    def test_ticket_ids_unique(self):
        ids = {self.new_issue().ticket_id for _ in range(40)}
        self.assertEqual(len(ids), 40)

    def test_my_issues_isolated(self):
        mine, theirs = self.new_issue(), self.new_issue(self.other, title="Bob's secret issue")
        self.client.login(username="alice", password=PW)
        r = self.client.get(reverse("my_issues"))
        self.assertContains(r, mine.ticket_id)
        self.assertNotContains(r, theirs.ticket_id)

    def test_student_cannot_open_others_issue(self):
        theirs = self.new_issue(self.other)
        self.client.login(username="alice", password=PW)
        self.assertEqual(self.client.get(reverse("issue_detail", args=[theirs.ticket_id])).status_code, 404)

    def test_student_cannot_use_staff_pages_or_actions(self):
        issue = self.new_issue()
        self.client.login(username="alice", password=PW)
        self.assertEqual(self.client.get(reverse("staff_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("staff_issues")).status_code, 403)
        r = self.client.post(reverse("issue_action", args=[issue.ticket_id, "status"]), {"status": "closed"})
        self.assertEqual(r.status_code, 403)
        issue.refresh_from_db()
        self.assertEqual(issue.status, "open")

    def test_anonymous_redirected(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_staff_cannot_submit_as_student_page(self):
        self.client.login(username="sam", password=PW)
        self.assertEqual(self.client.get(reverse("issue_create")).status_code, 403)


class WorkflowTests(Base):
    def test_assignment_and_activity(self):
        issue = self.new_issue()
        services.assign_issue(issue, self.staff, self.staff2)
        issue.refresh_from_db()
        self.assertEqual(issue.assigned_to, self.staff)
        self.assertTrue(issue.activities.filter(event_type="assigned").exists())

    def test_cannot_assign_student(self):
        with self.assertRaises(ValidationError):
            services.assign_issue(self.new_issue(), self.other, self.staff)

    def test_student_cannot_assign_or_respond(self):
        issue = self.new_issue()
        with self.assertRaises(PermissionDenied):
            services.assign_issue(issue, self.staff, self.student)
        with self.assertRaises(PermissionDenied):
            services.add_response(issue, self.student, "I am staff!")

    def test_status_flow_and_resolved_timestamp(self):
        issue = self.new_issue()
        services.change_status(issue, "in_progress", self.staff)
        self.assertIsNone(issue.resolved_at)
        services.change_status(issue, "resolved", self.staff)
        self.assertIsNotNone(issue.resolved_at)
        services.change_status(issue, "in_progress", self.staff)  # reopen
        self.assertIsNone(issue.resolved_at)
        services.change_status(issue, "resolved", self.staff)
        services.change_status(issue, "closed", self.staff)
        kinds = list(issue.activities.values_list("event_type", flat=True))
        self.assertEqual(kinds, ["submitted", "started", "resolved", "reopened", "resolved", "closed"])

    def test_invalid_transition(self):
        issue = self.new_issue()
        with self.assertRaises(ValidationError):
            services.change_status(issue, "resolved", self.staff)  # open -> resolved not allowed
        services.change_status(issue, "closed", self.staff)
        with self.assertRaises(ValidationError):
            services.change_status(issue, "in_progress", self.staff)  # closed is final

    def test_staff_response_visible_to_student(self):
        issue = self.new_issue()
        self.client.login(username="sam", password=PW)
        r = self.client.post(reverse("issue_action", args=[issue.ticket_id, "respond"]), {"message": "Checking now."})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(issue.responses.get().staff, self.staff)
        self.assertTrue(issue.activities.filter(event_type="response").exists())
        self.client.login(username="alice", password=PW)
        self.assertContains(self.client.get(reverse("issue_detail", args=[issue.ticket_id])), "Checking now.")

    def test_staff_web_actions(self):
        issue = self.new_issue()
        self.client.login(username="sam", password=PW)
        self.client.post(reverse("issue_action", args=[issue.ticket_id, "assign"]), {"assignee": self.staff2.pk})
        self.client.post(reverse("issue_action", args=[issue.ticket_id, "priority"]), {"priority": "low"})
        self.client.post(reverse("issue_action", args=[issue.ticket_id, "status"]), {"status": "in_progress"})
        issue.refresh_from_db()
        self.assertEqual((issue.assigned_to, issue.priority, issue.status), (self.staff2, "low", "in_progress"))


class SearchAndStatsTests(Base):
    def setUp(self):
        super().setUp()
        self.a = self.new_issue(title="Wi-Fi down", category="technical", priority="low")
        self.b = self.new_issue(title="Fees receipt", category="payment", priority="high")
        services.change_status(self.b, "in_progress", self.staff)

    def test_filters(self):
        qs = Issue.objects.all()
        self.assertEqual(list(services.filter_issues(qs, {"q": "wi-fi"})), [self.a])
        self.assertEqual(list(services.filter_issues(qs, {"category": "payment"})), [self.b])
        self.assertEqual(list(services.filter_issues(qs, {"status": "in_progress"})), [self.b])
        self.assertEqual(list(services.filter_issues(qs, {"priority": "low"})), [self.a])
        self.assertEqual(services.filter_issues(qs, {"assigned": "unassigned"}).count(), 2)

    def test_staff_list_search_page(self):
        self.client.login(username="sam", password=PW)
        r = self.client.get(reverse("staff_issues"), {"q": "Fees"})
        self.assertContains(r, self.b.ticket_id)
        self.assertNotContains(r, self.a.ticket_id)
        self.assertContains(self.client.get(reverse("staff_issues"), {"q": "zzzz"}), "No issues found")

    def test_counts_and_rate(self):
        c = services.issue_counts(Issue.objects.all())
        self.assertEqual((c["total"], c["open"], c["in_progress"], c["resolved"]), (2, 1, 1, 0))
        self.assertEqual(c["resolution_rate"], 0.0)
        services.change_status(self.b, "resolved", self.staff)
        c = services.issue_counts(Issue.objects.all())
        self.assertEqual((c["resolved"], c["resolution_rate"]), (1, 50.0))

    def test_empty_stats(self):
        Issue.objects.all().delete()
        self.assertIsNone(services.issue_counts(Issue.objects.all())["resolution_rate"])
        self.assertIsNone(services.average_first_response(Issue.objects.all()))

    def test_first_response_average(self):
        services.add_response(self.a, self.staff, "Hello there")
        self.assertIsNotNone(services.average_first_response(Issue.objects.all()))

    def test_dashboards_render_real_numbers(self):
        self.client.login(username="sam", password=PW)
        r = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["counts"]["total"], 2)
        self.assertEqual(r.context["this_week"], 2)
        self.assertEqual(self.client.get(reverse("reports")).status_code, 200)
        self.client.login(username="alice", password=PW)
        r = self.client.get(reverse("dashboard"))
        self.assertEqual(r.context["counts"]["total"], 2)
        self.client.login(username="bob", password=PW)
        self.assertEqual(self.client.get(reverse("dashboard")).context["counts"]["total"], 0)


class ApiTests(Base):
    def setUp(self):
        super().setUp()
        self.api = APIClient()

    def test_requires_authentication(self):
        self.assertEqual(self.api.get("/api/issues/").status_code, 403)

    def test_student_create_and_list_own_only(self):
        self.new_issue(self.other)
        self.api.force_authenticate(self.student)
        r = self.api.post("/api/issues/", {**self.issue_data, "status": "closed", "student": self.other.pk}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "open")  # protected field ignored
        self.assertEqual(Issue.objects.get(pk=r.data["id"]).student, self.student)
        lst = self.api.get("/api/issues/")
        self.assertEqual(lst.data["count"], 1)

    def test_api_validation_error_shape(self):
        self.api.force_authenticate(self.student)
        r = self.api.post("/api/issues/", {"title": "x"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.data)

    def test_student_cannot_see_or_patch_others(self):
        theirs = self.new_issue(self.other)
        self.api.force_authenticate(self.student)
        self.assertEqual(self.api.get(f"/api/issues/{theirs.pk}/").status_code, 404)
        self.assertEqual(self.api.patch(f"/api/issues/{theirs.pk}/", {"status": "closed"}, format="json").status_code, 403)
        mine = self.new_issue()
        self.assertEqual(self.api.patch(f"/api/issues/{mine.pk}/", {"status": "closed"}, format="json").status_code, 403)
        self.assertEqual(self.api.delete(f"/api/issues/{mine.pk}/").status_code, 403)

    def test_staff_patch_and_activity(self):
        issue = self.new_issue()
        self.api.force_authenticate(self.staff)
        r = self.api.patch(f"/api/issues/{issue.pk}/", {"status": "in_progress", "priority": "low",
                                                        "assigned_to": self.staff.pk}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["status"], "in_progress")
        self.assertEqual(self.api.get(f"/api/issues/{issue.pk}/activity/").data[-1]["event_type"], "started")
        bad = self.api.patch(f"/api/issues/{issue.pk}/", {"status": "open"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_responses_endpoint(self):
        issue = self.new_issue()
        self.api.force_authenticate(self.student)
        self.assertEqual(self.api.post(f"/api/issues/{issue.pk}/responses/", {"message": "hi"}, format="json").status_code, 403)
        self.api.force_authenticate(self.staff)
        self.assertEqual(self.api.post(f"/api/issues/{issue.pk}/responses/", {"message": "On it."}, format="json").status_code, 201)
        self.api.force_authenticate(self.student)
        self.assertEqual(len(self.api.get(f"/api/issues/{issue.pk}/responses/").data), 1)

    def test_delete_is_soft_and_admin_only(self):
        issue = self.new_issue()
        admin = make_user("root", "admin")
        self.api.force_authenticate(self.staff)
        self.assertEqual(self.api.delete(f"/api/issues/{issue.pk}/").status_code, 403)
        self.api.force_authenticate(admin)
        self.assertEqual(self.api.delete(f"/api/issues/{issue.pk}/").status_code, 200)
        issue.refresh_from_db()
        self.assertEqual(issue.status, "closed")

    def test_stats_and_me(self):
        self.new_issue()
        self.api.force_authenticate(self.staff)
        self.assertEqual(self.api.get("/api/stats/").data["total"], 1)
        self.assertEqual(self.api.get("/api/me/").data["role"], "staff")
        self.api.force_authenticate(self.student)
        self.assertEqual(self.api.get("/api/me/").data["role"], "student")

    def test_api_search(self):
        self.new_issue(title="Printer jam")
        self.new_issue(title="Wi-Fi slow")
        self.api.force_authenticate(self.student)
        self.assertEqual(self.api.get("/api/issues/", {"q": "printer"}).data["count"], 1)
