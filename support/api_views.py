from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.views import exception_handler as drf_exception_handler

from . import services
from .models import Issue
from .permissions import IsAdminRole, IsStaffMember, is_staff_member
from .serializers import (AssignSerializer, IssueActivitySerializer, IssueResponseSerializer,
                          IssueSerializer, IssueUpdateSerializer, MeSerializer)


def exception_handler(exc, context):
    """Consistent JSON errors: {"error": {"status": 400, "message": "...", "details": {...}}}."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    details = response.data
    message = details.get("detail") if isinstance(details, dict) and "detail" in details else "Request failed."
    response.data = {"error": {"status": response.status_code, "message": str(message),
                               "details": None if isinstance(details, dict) and "detail" in details else details}}
    return response


def _wrap(callable_):
    """Run a service function and convert Django errors to DRF errors."""
    try:
        return callable_()
    except DjangoValidationError as exc:
        raise ValidationError({"non_field_errors": exc.messages})
    except DjangoPermissionDenied:
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied()


class IssueViewSet(viewsets.ModelViewSet):
    """/api/issues/ - students see only their own tickets; staff see all."""
    serializer_class = IssueSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Issue.objects.select_related("student", "assigned_to")
        if not is_staff_member(self.request.user):
            qs = qs.filter(student=self.request.user)
        return services.filter_issues(qs, self.request.query_params)

    def get_permissions(self):
        if self.action == "destroy":
            return [IsAuthenticated(), IsAdminRole()]
        if self.action in ("partial_update", "update", "assign"):
            return [IsAuthenticated(), IsStaffMember()]
        if self.action == "create":
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        if is_staff_member(request.user):
            return Response({"error": {"status": 403, "message": "Only students submit issues.", "details": None}},
                            status=http.HTTP_403_FORBIDDEN)
        serializer = IssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issue = services.create_issue(request.user, **serializer.validated_data)  # owner = session user
        return Response(IssueSerializer(issue).data, status=http.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        issue = self.get_object()
        body = IssueUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if not data:
            raise ValidationError({"non_field_errors": ["Provide status, priority or assigned_to."]})

        def apply():
            if "priority" in data and data["priority"] != issue.priority:
                services.change_priority(issue, data["priority"], request.user)
            if "assigned_to" in data and (data["assigned_to"].pk if data["assigned_to"] else None) != issue.assigned_to_id:
                services.assign_issue(issue, data["assigned_to"], request.user)
            if "status" in data and data["status"] != issue.status:
                services.change_status(issue, data["status"], request.user)
        _wrap(apply)
        issue.refresh_from_db()
        return Response(IssueSerializer(issue).data)

    def destroy(self, request, *args, **kwargs):
        """Soft delete: audit history matters, so 'delete' closes the ticket instead of erasing it."""
        issue = self.get_object()
        if issue.is_closed:
            return Response({"detail": "Issue is already closed/archived."}, status=http.HTTP_200_OK)
        if issue.status == Issue.Status.OPEN:
            services.change_status(issue, Issue.Status.IN_PROGRESS, request.user)
        if issue.status == Issue.Status.IN_PROGRESS:
            services.change_status(issue, Issue.Status.RESOLVED, request.user)
        services.change_status(issue, Issue.Status.CLOSED, request.user)
        return Response({"detail": "Issue archived (closed). Its history is preserved."})

    @action(detail=True, methods=["get", "post"], url_path="responses")
    def responses(self, request, pk=None):
        issue = self.get_object()  # students can only reach their own issues
        if request.method == "GET":
            return Response(IssueResponseSerializer(issue.responses.select_related("staff"), many=True).data)
        if not is_staff_member(request.user):
            return Response({"error": {"status": 403, "message": "Only staff can respond.", "details": None}},
                            status=http.HTTP_403_FORBIDDEN)
        serializer = IssueResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = _wrap(lambda: services.add_response(issue, request.user, serializer.validated_data["message"]))
        return Response(IssueResponseSerializer(response).data, status=http.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request, pk=None):
        issue = self.get_object()
        return Response(IssueActivitySerializer(issue.activities.select_related("actor"), many=True).data)

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, pk=None):
        issue = self.get_object()
        body = AssignSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        _wrap(lambda: services.assign_issue(issue, body.validated_data["assigned_to"], request.user))
        issue.refresh_from_db()
        return Response(IssueSerializer(issue).data)


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class StatsView(APIView):
    """Staff: system-wide numbers. Students: their own numbers."""
    def get(self, request):
        if is_staff_member(request.user):
            qs = Issue.objects.all()
            data = services.issue_counts(qs)
            data["this_week"] = qs.filter(created_at__gte=services.week_start()).count()
            avg = services.average_first_response(qs)
            data["avg_first_response_seconds"] = int(avg.total_seconds()) if avg else None
            data["by_category"] = {l: n for l, n, _ in services.breakdown(qs, "category", Issue.Category.choices)}
            data["by_status"] = {l: n for l, n, _ in services.breakdown(qs, "status", Issue.Status.choices)}
        else:
            data = services.issue_counts(Issue.objects.filter(student=request.user))
        return Response(data)


class CategoriesView(APIView):
    def get(self, request):
        return Response({
            "categories": [{"value": v, "label": l} for v, l in Issue.Category.choices],
            "priorities": [{"value": v, "label": l} for v, l in Issue.Priority.choices],
            "statuses": [{"value": v, "label": l} for v, l in Issue.Status.choices],
        })
