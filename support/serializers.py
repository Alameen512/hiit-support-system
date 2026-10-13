from django.contrib.auth import get_user_model
from rest_framework import serializers

from . import services
from .models import Issue, IssueActivity, IssueResponse

User = get_user_model()


class IssueSerializer(serializers.ModelSerializer):
    """Read/create serializer. Ownership and workflow fields are read-only."""
    student_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Issue
        fields = ["id", "ticket_id", "title", "description", "category", "category_display",
                  "priority", "priority_display", "status", "status_display", "location",
                  "student_name", "assigned_to", "assigned_to_name",
                  "created_at", "updated_at", "resolved_at"]
        read_only_fields = ["id", "ticket_id", "status", "assigned_to", "created_at", "updated_at", "resolved_at"]

    def get_student_name(self, obj):
        return services.display_name(obj.student)

    def get_assigned_to_name(self, obj):
        return services.display_name(obj.assigned_to) if obj.assigned_to else None

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError("Title must be at least 5 characters.")
        return value

    def validate_description(self, value):
        value = value.strip()
        if len(value) < 15:
            raise serializers.ValidationError("Description must be at least 15 characters.")
        return value


class IssueUpdateSerializer(serializers.Serializer):
    """Staff-only PATCH body. Only these three fields can ever be changed."""
    status = serializers.ChoiceField(choices=Issue.Status.choices, required=False)
    priority = serializers.ChoiceField(choices=Issue.Priority.choices, required=False)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)


class AssignSerializer(serializers.Serializer):
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), allow_null=True)


class IssueResponseSerializer(serializers.ModelSerializer):
    staff_name = serializers.SerializerMethodField()

    class Meta:
        model = IssueResponse
        fields = ["id", "message", "staff_name", "created_at"]
        read_only_fields = ["id", "staff_name", "created_at"]

    def get_staff_name(self, obj):
        return services.display_name(obj.staff)


class IssueActivitySerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = IssueActivity
        fields = ["id", "event_type", "description", "actor_name", "created_at"]

    def get_actor_name(self, obj):
        return services.display_name(obj.actor) if obj.actor else None


class MeSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="profile.role", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role"]
        read_only_fields = ["id", "username", "role"]
