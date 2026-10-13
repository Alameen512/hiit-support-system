"""Create demonstration users and tickets. Safe to re-run (uses get_or_create).

    python manage.py seed_demo --password "ChooseSomething!42"

Refuses to run when DEBUG is off unless --force is given, so weak demo accounts
are never created on a public production site by accident.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from support import services
from support.models import Issue, IssueActivity, Profile

User = get_user_model()

STAFF = [("demo_staff1", "Adaeze", "Okafor", "Technical Support"),
         ("demo_staff2", "John", "Martins", "Laboratory"),
         ("demo_staff3", "Sarah", "Bello", "Administration")]
STUDENTS = [("demo_student1", "Tolu", "Adebayo"), ("demo_student2", "Chinedu", "Eze"),
            ("demo_student3", "Fatima", "Yusuf"), ("demo_student4", "Ngozi", "Obi")]

C, P, S = Issue.Category, Issue.Priority, Issue.Status
ISSUES = [  # (student idx, title, category, priority, final status, staff idx or None, reply)
    (0, "Computer not working in IT Lab 2", C.LABORATORY, P.HIGH, S.IN_PROGRESS, 1, "A technician is checking the power supply."),
    (0, "Course registration issue", C.COURSE, P.MEDIUM, S.OPEN, None, None),
    (0, "Certificate not received", C.CERTIFICATE, P.LOW, S.RESOLVED, 2, "Your certificate has been issued; collect it at the front desk."),
    (1, "Cannot log in to the student portal", C.TECHNICAL, P.HIGH, S.RESOLVED, 0, "Password reset completed. Please try again."),
    (1, "Wrong amount on payment receipt", C.PAYMENT, P.MEDIUM, S.IN_PROGRESS, 2, "We are reconciling the payment with accounts."),
    (1, "Timetable clash between two modules", C.ACADEMIC, P.MEDIUM, S.OPEN, None, None),
    (2, "Projector not working in Hall B", C.TECHNICAL, P.LOW, S.CLOSED, 0, "Projector bulb replaced."),
    (2, "Need a letter of introduction for SIWES", C.ADMINISTRATIVE, P.MEDIUM, S.RESOLVED, 2, "Letter is ready for pickup."),
    (2, "Missing marks for Python assessment", C.ACADEMIC, P.HIGH, S.IN_PROGRESS, 1, "Checking the score sheet with the instructor."),
    (3, "Lab computer keeps restarting", C.LABORATORY, P.MEDIUM, S.OPEN, None, None),
    (3, "Unable to add elective course", C.COURSE, P.HIGH, S.IN_PROGRESS, 0, "The elective list is being updated."),
    (3, "Duplicate payment charged", C.PAYMENT, P.HIGH, S.OPEN, None, None),
    (0, "Wi-Fi is very slow in Block A", C.TECHNICAL, P.LOW, S.OPEN, None, None),
    (1, "Request for course outline", C.ACADEMIC, P.LOW, S.RESOLVED, 1, "Outline emailed to you."),
    (2, "Name misspelt on certificate", C.CERTIFICATE, P.MEDIUM, S.IN_PROGRESS, 2, "Corrections sent to the registry."),
    (3, "Other: locker key request", C.OTHER, P.LOW, S.OPEN, None, None),
]


class Command(BaseCommand):
    help = "Create demo students, staff and tickets (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Password for all demo accounts.")
        parser.add_argument("--force", action="store_true", help="Allow running with DEBUG off.")

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError("Refusing to create demo accounts with DEBUG off. Use --force if you really mean it.")
        pw = opts["password"]
        staff = []
        for username, first, last, dept in STAFF:
            u, created = User.objects.get_or_create(username=username, defaults={
                "first_name": first, "last_name": last, "email": f"{username}@demo.hiit.example"})
            if created:
                u.set_password(pw)
                u.save()
            Profile.objects.filter(user=u).update(role=Profile.Role.STAFF, department=dept)
            staff.append(u)
        students = []
        for i, (username, first, last) in enumerate(STUDENTS):
            u, created = User.objects.get_or_create(username=username, defaults={
                "first_name": first, "last_name": last, "email": f"{username}@demo.hiit.example"})
            if created:
                u.set_password(pw)
                u.save()
            Profile.objects.filter(user=u).update(matric_number=f"DEMO/{2024000 + i}")
            students.append(u)

        made = 0
        for n, (si, title, cat, pri, final, ti, reply) in enumerate(ISSUES):
            student = students[si]
            if Issue.objects.filter(student=student, title=title).exists():
                continue
            issue = services.create_issue(student, title=title, description=f"{title}. Please assist as soon as possible. "
                                          "This is demonstration data.", category=cat, priority=pri,
                                          location="IT Lab 2" if cat == C.LABORATORY else "")
            if ti is not None:
                actor = staff[ti]
                services.assign_issue(issue, actor, actor)
                if final != S.OPEN:
                    services.change_status(issue, S.IN_PROGRESS, actor)
                if reply:
                    services.add_response(issue, actor, reply)
                if final in (S.RESOLVED, S.CLOSED):
                    services.change_status(issue, S.RESOLVED, actor)
                if final == S.CLOSED:
                    services.change_status(issue, S.CLOSED, actor)
            # Spread creation dates over the last two weeks so the reports look alive.
            created_at = timezone.now() - timedelta(days=n % 12, hours=n)
            Issue.objects.filter(pk=issue.pk).update(
                created_at=created_at,
                resolved_at=(created_at + timedelta(hours=6 + n)) if final in (S.RESOLVED, S.CLOSED) else None)
            issue.responses.update(created_at=created_at + timedelta(hours=2))
            IssueActivity.objects.filter(issue=issue).update(created_at=created_at + timedelta(minutes=30))
            made += 1
        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {len(staff)} staff, {len(students)} students, {made} new tickets."))
