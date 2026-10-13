from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),  # POST only (Django 5)
    path("dashboard/", views.dashboard, name="dashboard"),
    path("issues/", views.my_issues, name="my_issues"),
    path("issues/new/", views.issue_create, name="issue_create"),
    path("issues/<str:ticket_id>/", views.issue_detail, name="issue_detail"),
    path("issues/<str:ticket_id>/<str:action>/", views.issue_action, name="issue_action"),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
    path("staff/issues/", views.staff_issues, name="staff_issues"),
    path("staff/students/", views.staff_students, name="staff_students"),
    path("staff/members/", views.staff_members, name="staff_members"),
    path("staff/reports/", views.reports, name="reports"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/password/", views.HiitPasswordChangeView.as_view(), name="password_change"),
    path("info/<slug:slug>/", views.info_page, name="info"),
]
