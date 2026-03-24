from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CompanyViewSet,
    JobViewSet,
    approve_company,
    approve_job,
    approve_pending_user,
    delete_user_permanently,
    list_pending_companies,
    list_pending_jobs,
    list_pending_users,
    reapprove_user,
    register_pending_user,
    reject_company,
    reject_job,
    reject_pending_user,
    revoke_user,
    subadmin_profile,
    UserListView,
    SalaryAggregateView,
)


router = DefaultRouter()
router.register(r"jobs", JobViewSet, basename="job")
router.register(r"companies", CompanyViewSet, basename="company")

urlpatterns = [
    path("jobs/pending/", list_pending_jobs),
    path("jobs/salaries-aggregate/", SalaryAggregateView.as_view(), name="salaries-aggregate"),
    path("companies/pending/", list_pending_companies),
    path("companies/bulk_upload/", CompanyViewSet.as_view({"post": "bulk_upload"})),
    path("", include(router.urls)),
    path("auth/register/", register_pending_user),
    path("auth/users/", UserListView.as_view(), name="auth-users"),
    path("auth/pending-users/", list_pending_users),
    path("auth/approve-user/<int:pk>/", approve_pending_user),
    path("auth/reject-user/<int:pk>/", reject_pending_user),
    path("auth/revoke-user/<int:pk>/", revoke_user),
    path("auth/reapprove-user/<int:pk>/", reapprove_user),
    path("auth/delete-user/<int:pk>/", delete_user_permanently),
    path("auth/profile/", subadmin_profile),
    path("jobs/<int:pk>/approve/", approve_job),
    path("jobs/<int:pk>/reject/", reject_job),
    path("companies/<int:pk>/approve/", approve_company),
    path("companies/<int:pk>/reject/", reject_company),
]
