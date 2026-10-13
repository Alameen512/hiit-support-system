import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("student", "Student"), ("staff", "Staff"), ("admin", "Administrator")], default="student", max_length=10)),
                ("phone", models.CharField(blank=True, max_length=20)),
                ("matric_number", models.CharField(blank=True, max_length=30)),
                ("department", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Issue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ticket_id", models.CharField(editable=False, max_length=20, unique=True)),
                ("title", models.CharField(max_length=150)),
                ("description", models.TextField(max_length=3000)),
                ("category", models.CharField(choices=[("technical", "Technical"), ("academic", "Academic"), ("administrative", "Administrative"), ("course_registration", "Course/Registration"), ("laboratory", "Laboratory"), ("certificate", "Certificate"), ("payment", "Payment"), ("other", "Other")], max_length=30)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")], default="medium", max_length=10)),
                ("status", models.CharField(choices=[("open", "Open"), ("in_progress", "In Progress"), ("resolved", "Resolved"), ("closed", "Closed")], default="open", max_length=15)),
                ("location", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_issues", to=settings.AUTH_USER_MODEL)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="issues", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["status"], name="issue_status_idx"),
                    models.Index(fields=["category"], name="issue_category_idx"),
                    models.Index(fields=["created_at"], name="issue_created_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="IssueResponse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField(max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("issue", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="responses", to="support.issue")),
                ("staff", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="issue_responses", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="IssueActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("submitted", "Issue submitted"), ("assigned", "Assignment changed"), ("priority", "Priority changed"), ("started", "Work started"), ("response", "Staff response added"), ("resolved", "Issue resolved"), ("closed", "Issue closed"), ("reopened", "Issue reopened")], max_length=15)),
                ("description", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="issue_activities", to=settings.AUTH_USER_MODEL)),
                ("issue", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="support.issue")),
            ],
            options={"ordering": ["created_at", "id"], "verbose_name_plural": "issue activities"},
        ),
    ]
