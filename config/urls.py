from django.contrib import admin
from django.urls import include, path

handler403 = "support.views.error_403"
handler404 = "support.views.error_404"
handler500 = "support.views.error_500"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("support.api_urls")),
    path("", include("support.urls")),
]
