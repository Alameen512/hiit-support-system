from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import Issue, IssueActivity, IssueResponse, Profile

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0


admin.site.unregister(User)


@admin.register(User)
class HiitUserAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active")
    list_filter = ("profile__role", "is_active")
    list_select_related = ("profile",)

    def get_inline_instances(self, request, obj=None):
        # The Profile is auto-created by a signal, so only show the inline when editing.
        return super().get_inline_instances(request, obj) if obj else []

    @admin.display(description="Role", ordering="profile__role")
    def role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, "profile") else "-"


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "matric_number", "created_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email", "matric_number")
    readonly_fields = ("created_at",)


class ResponseInline(admin.TabularInline):
    model = IssueResponse
    extra = 0
    readonly_fields = ("created_at",)


class ActivityInline(admin.TabularInline):
    model = IssueActivity
    extra = 0
    readonly_fields = ("event_type", "description", "actor", "created_at")
    can_delete = False


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("ticket_id", "title", "student", "category", "priority", "status", "assigned_to", "created_at")
    list_filter = ("status", "category", "priority")
    search_fields = ("ticket_id", "title", "student__username", "student__email")
    ordering = ("-created_at",)
    readonly_fields = ("ticket_id", "created_at", "updated_at", "resolved_at")
    list_select_related = ("student", "assigned_to")
    inlines = [ResponseInline, ActivityInline]


@admin.register(IssueResponse)
class IssueResponseAdmin(admin.ModelAdmin):
    list_display = ("issue", "staff", "created_at")
    search_fields = ("issue__ticket_id", "message")
    readonly_fields = ("created_at",)


@admin.register(IssueActivity)
class IssueActivityAdmin(admin.ModelAdmin):
    list_display = ("issue", "event_type", "actor", "created_at")
    list_filter = ("event_type",)
    search_fields = ("issue__ticket_id", "description")
    readonly_fields = ("created_at",)
