from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import Company, Job, PendingUser, SubadminProfile
from .permissions import IsAdminUserOrReadOnly
from .serializers import CompanySerializer, JobSerializer, PendingUserSerializer, SubadminProfileSerializer


class CompanyViewSet(viewsets.ModelViewSet):
    serializer_class = CompanySerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        queryset = Company.objects.all().order_by("name")

        if user and user.is_authenticated and user.is_staff:
            return queryset
        elif user and user.is_authenticated:
            return queryset.filter(Q(status="approved") | Q(submittedBy=user.username))
        else:
            return queryset.filter(status="approved")

    def perform_create(self, serializer):
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            serializer.save(status="approved", submittedBy=user.username)
        else:
            serializer.save(status="pending", submittedBy=getattr(user, "username", "unknown"))

    def perform_update(self, serializer):
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            serializer.save()
        else:
            serializer.save(status="pending")


class JobViewSet(viewsets.ModelViewSet):
    serializer_class = JobSerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        queryset = Job.objects.all()

        from django.utils import timezone

        # 1. Base visibility rules
        if user and user.is_authenticated and user.is_staff:
            # Admin users see ALL jobs (approved + pending + expired)
            pass
        elif user and user.is_authenticated:
            # Subadmin sees approved jobs (from everyone) + their own pending jobs
            # Expired jobs are intentionally NOT filtered out here so they show in the dashboard
            queryset = queryset.filter(Q(status="approved") | Q(submittedBy=user.username))
        else:
            # Public sees only approved, unexpired jobs
            queryset = queryset.filter(status="approved").filter(
                Q(expiryDate__isnull=True) | Q(expiryDate__gte=timezone.now())
            )

        # 2. URL parameter filtering
        company = self.request.query_params.get("company")
        role = self.request.query_params.get("role")
        q = self.request.query_params.get("q")

        if company:
            queryset = queryset.filter(company__iexact=company)
        if role:
            queryset = queryset.filter(title__iexact=role)
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(company__icontains=q) | Q(description__icontains=q))

        return queryset.order_by("-postedAt")

    def perform_create(self, serializer):
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            serializer.save(status="approved", submittedBy=user.username)
        else:
            serializer.save(status="pending", submittedBy=getattr(user, "username", "unknown"))

    def perform_update(self, serializer):
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            # Admin edits stay approved (or whatever status they set)
            serializer.save()
        else:
            # Subadmin edits require re-approval before going live
            serializer.save(status="pending")

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def request_delete(self, request, pk=None):
        """Subadmin (or admin): request to delete a job."""
        job = self.get_object()
        # Only admins or the job author can request deletion
        if not request.user.is_staff and job.submittedBy != request.user.username:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        job.status = "pending_deletion"
        job.save()
        return Response({"detail": "Deletion requested."})

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def approve_deletion(self, request, pk=None):
        """Admin: permanently delete a job pending deletion."""
        job = self.get_object()
        if job.status != "pending_deletion":
            return Response({"detail": "Job is not pending deletion."}, status=status.HTTP_400_BAD_REQUEST)
        job.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def reject_deletion(self, request, pk=None):
        """Admin: reject deletion request, restoring job to approved."""
        job = self.get_object()
        if job.status != "pending_deletion":
            return Response({"detail": "Job is not pending deletion."}, status=status.HTTP_400_BAD_REQUEST)
        job.status = "approved"
        job.save()
        return Response({"detail": "Deletion rejected. Job restored."})


# ── Job Approval Endpoints (admin only) ──────────────────
@api_view(["GET"])
@permission_classes([IsAdminUser])
def list_pending_jobs(request):
    """Admin: list all jobs pending review."""
    jobs = Job.objects.filter(status="pending").order_by("-postedAt")
    return Response(JobSerializer(jobs, many=True).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def approve_job(request, pk):
    """Admin: approve a pending job — makes it live."""
    try:
        job = Job.objects.get(pk=pk, status="pending")
    except Job.DoesNotExist:
        return Response({"detail": "Pending job not found."}, status=status.HTTP_404_NOT_FOUND)
    job.status = "approved"
    job.save()
    return Response({"detail": f'"{job.title}" is now live.'})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def reject_job(request, pk):
    """Admin: reject a pending job."""
    try:
        job = Job.objects.get(pk=pk)
    except Job.DoesNotExist:
        return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
    job.status = "rejected"
    job.save()
    return Response({"detail": f'"{job.title}" has been rejected.'})


# ── Company Approval Endpoints (admin only) ────────────────
@api_view(["GET"])
@permission_classes([IsAdminUser])
def list_pending_companies(request):
    """Admin: list all companies pending review."""
    companies = Company.objects.filter(status="pending").order_by("name")
    return Response(CompanySerializer(companies, many=True).data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def approve_company(request, pk):
    """Admin: approve a pending company."""
    try:
        company = Company.objects.get(pk=pk, status="pending")
    except Company.DoesNotExist:
        return Response({"detail": "Pending company not found."}, status=status.HTTP_404_NOT_FOUND)
    company.status = "approved"
    company.save()
    return Response({"detail": f'"{company.name}" is now approved.'})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def reject_company(request, pk):
    """Admin: reject a pending company."""
    try:
        company = Company.objects.get(pk=pk)
    except Company.DoesNotExist:
        return Response({"detail": "Company not found."}, status=status.HTTP_404_NOT_FOUND)
    company.status = "rejected"
    company.save()
    return Response({"detail": f'"{company.name}" has been rejected.'})


# ── Subadmin Profile ──────────────────────────────────────
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def subadmin_profile(request):
    """GET or PATCH the logged-in user's SubadminProfile."""
    profile, _ = SubadminProfile.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return Response(SubadminProfileSerializer(profile).data)
    serializer = SubadminProfileSerializer(profile, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Subadmin Registration ─────────────────────────────────
@api_view(["POST"])
@permission_classes([AllowAny])
def register_pending_user(request):
    """Public: submit a subadmin registration request."""
    username = request.data.get("username", "").strip()
    email = request.data.get("email", "").strip()
    password = request.data.get("password", "")

    if not username or not email or not password:
        return Response({"detail": "username, email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username=username).exists() or PendingUser.objects.filter(username=username).exists():
        return Response({"detail": "Username already taken."}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email=email).exists() or PendingUser.objects.filter(email=email).exists():
        return Response({"detail": "Email already registered."}, status=status.HTTP_400_BAD_REQUEST)

    pending = PendingUser.objects.create(
        username=username,
        email=email,
        password=make_password(password),
        status="pending",
    )
    return Response(PendingUserSerializer(pending).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def list_pending_users(request):
    """Admin only: list all pending registration requests."""
    pending = PendingUser.objects.all().order_by("-requestedAt")
    serializer = PendingUserSerializer(pending, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def approve_pending_user(request, pk):
    """Admin only: approve a pending user — creates a real Django User."""
    try:
        pending = PendingUser.objects.get(pk=pk)
    except PendingUser.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if pending.status == "approved":
        return Response({"detail": "Already approved."}, status=status.HTTP_400_BAD_REQUEST)

    # Create the real user with the hashed password
    User.objects.create(
        username=pending.username,
        email=pending.email,
        password=pending.password,  # already hashed
        is_staff=False,
        is_active=True,
    )
    # Auto-create an empty SubadminProfile for this user
    new_user = User.objects.get(username=pending.username)
    SubadminProfile.objects.get_or_create(user=new_user)
    pending.status = "approved"
    pending.save()
    return Response({"detail": f"{pending.username} approved and can now log in."})


@api_view(["DELETE"])
@permission_classes([IsAdminUser])
def reject_pending_user(request, pk):
    """Admin only: reject and remove a pending registration."""
    try:
        pending = PendingUser.objects.get(pk=pk)
    except PendingUser.DoesNotExist:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    pending.status = "rejected"
    pending.save()
    return Response({"detail": f"{pending.username} has been rejected."})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def revoke_user(request, pk):
    """Admin only: revoke an approved user's access (blocks login)."""
    try:
        pending = PendingUser.objects.get(pk=pk, status="approved")
    except PendingUser.DoesNotExist:
        return Response({"detail": "Approved user not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        django_user = User.objects.get(username=pending.username)
        django_user.is_active = False
        django_user.save()
    except User.DoesNotExist:
        pass

    pending.status = "revoked"
    pending.save()
    return Response({"detail": f"{pending.username}\u2019s access has been revoked."})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def reapprove_user(request, pk):
    """Admin only: re-activate a revoked user."""
    try:
        pending = PendingUser.objects.get(pk=pk, status="revoked")
    except PendingUser.DoesNotExist:
        return Response({"detail": "Revoked user not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        django_user = User.objects.get(username=pending.username)
        django_user.is_active = True
        django_user.save()
    except User.DoesNotExist:
        pass

    pending.status = "approved"
    pending.save()
    return Response({"detail": f"{pending.username}\u2019s access has been restored."})
