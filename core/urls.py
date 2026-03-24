from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenRefreshView,
)
from jobs.views import CustomTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("jobs.urls")),
    path("api/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/logout/", TokenBlacklistView.as_view(), name="token_blacklist"),
]
