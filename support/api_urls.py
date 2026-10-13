from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api_views

router = DefaultRouter()
router.register("issues", api_views.IssueViewSet, basename="api-issue")

urlpatterns = [
    path("me/", api_views.MeView.as_view(), name="api-me"),
    path("stats/", api_views.StatsView.as_view(), name="api-stats"),
    path("categories/", api_views.CategoriesView.as_view(), name="api-categories"),
    path("", include(router.urls)),
]
