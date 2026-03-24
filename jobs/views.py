from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import status, viewsets, filters, generics
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Company, Job, PendingUser, SubadminProfile
from .permissions import IsAdminUserOrReadOnly
from .serializers import CompanySerializer, JobSerializer, PendingUserSerializer, SubadminProfileSerializer, CustomTokenObtainPairSerializer

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class CompanyViewSet(viewsets.ModelViewSet):
    serializer_class = CompanySerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ["name", "website", "description"]
    filterset_fields = ["status", "submittedBy"]
    ordering_fields = ["name", "id"]
    ordering = ["name", "submittedBy"]

    def get_queryset(self):
        user = self.request.user
        import django.db.models as models
        
        # Annotate with the number of approved jobs
        queryset = Company.objects.annotate(
            job_count=models.Count('jobs', filter=models.Q(jobs__status='approved'))
        )

        if user and user.is_authenticated and user.is_staff:
            return queryset.order_by("name")
        elif user and user.is_authenticated:
            # Subadmins see approved companies + their own submitted companies
            return queryset.filter(Q(status="approved") | Q(submittedBy=user.username)).order_by("-job_count", "name")
        else:
            # Public sees only approved companies
            return queryset.filter(status="approved").order_by("-job_count", "name")

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

    @action(detail=False, methods=["post"])
    def bulk_upload(self, request):
        if "file" not in request.FILES:
            return Response({"error": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        
        file = request.FILES["file"]
        try:
            import json
            content = file.read().decode('utf-8')
            data = json.loads(content)
            
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, list):
                        data = val
                        break
                
            if not isinstance(data, list):
                return Response({"error": f"JSON file must contain a list of companies. Found {type(data).__name__} instead."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Invalid JSON file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        added = 0
        skipped = 0
        skipped_details = []
        errors = []

        user = request.user
        submitted_by = getattr(user, "username", "unknown")
        default_status = "approved" if user and user.is_authenticated and user.is_staff else "pending"

        for index, item in enumerate(data):
            name = item.get("name")
            website = item.get("website", "No URL")
            
            if not name:
                reason = "Missing company name"
                skipped_details.append({"row": index, "name": "Unknown", "reason": reason, "url": website})
                skipped += 1
                continue
            
            from .models import Company
            if Company.objects.filter(name__iexact=name).exists():
                reason = f"Company '{name}' already exists"
                skipped_details.append({"row": index, "name": name, "reason": reason, "url": website})
                skipped += 1
                continue
                
            serializer = self.get_serializer(data=item)
            if serializer.is_valid():
                serializer.save(status=default_status, submittedBy=submitted_by)
                added += 1
            else:
                err_msg = str(serializer.errors)
                errors.append({"row": index, "name": name, "error": err_msg, "url": website})
                skipped += 1

        return Response({
            "added": added,
            "skipped": skipped,
            "skipped_details": skipped_details,
            "errors": errors
        })


class JobViewSet(viewsets.ModelViewSet):
    serializer_class = JobSerializer
    permission_classes = [IsAdminUserOrReadOnly]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ["title", "location", "description", "company_obj__name"]
    filterset_fields = ["status"]
    ordering_fields = ["postedAt", "title", "id"]
    ordering = ["-postedAt"]

    def get_queryset(self):
        user = self.request.user
        queryset = Job.objects.all()

        from django.utils import timezone
        import django.db.models as models

        # 1. Base visibility rules
        if user and user.is_authenticated and user.is_staff:
            # Admin users see ALL jobs (approved + pending + expired)
            pass
        elif user and user.is_authenticated:
            # Subadmin sees approved jobs (from everyone) + their own pending jobs
            # Expired jobs are intentionally NOT filtered out here so they show in the dashboard
            queryset = queryset.filter(models.Q(status="approved") | models.Q(submittedBy=user.username))
        else:
            # Public sees only approved, unexpired jobs
            queryset = queryset.filter(status="approved").filter(
                models.Q(expiryDate__isnull=True) | models.Q(expiryDate__gte=timezone.now())
            )

        # 2. Custom array filters for arrays (e.g. types[]=a&types[]=b or jobType=a,b)
        params = self.request.query_params
        job_types = params.get("jobType")
        if job_types:
            queryset = queryset.filter(jobType__in=job_types.split(","))
            
        location_types = params.get("locationType")
        if location_types:
            queryset = queryset.filter(locationType__in=location_types.split(","))

        # Role / Company specific
        company = params.get("company")
        role = params.get("role")
        q = params.get("q")

        if company:
            queryset = queryset.filter(company_obj__name__icontains=company)
        if role:
            queryset = queryset.filter(title__icontains=role)
        if q:
            queryset = queryset.filter(models.Q(title__icontains=q) | models.Q(company_obj__name__icontains=q) | models.Q(description__icontains=q))

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

    @action(detail=False, methods=["post"])
    def bulk_upload(self, request):
        if "file" not in request.FILES:
            return Response({"error": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
        
        file = request.FILES["file"]
        try:
            import json
            content = file.read().decode('utf-8')
            data = json.loads(content)
            
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, list):
                        data = val
                        break
                
            if not isinstance(data, list):
                return Response({"error": f"JSON file must contain a list of jobs. Found {type(data).__name__} instead."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"Invalid JSON file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        added = 0
        skipped = 0
        skipped_details = []
        errors = []

        user = request.user
        submitted_by = getattr(user, "username", "unknown")
        default_status = "approved" if user and user.is_authenticated and user.is_staff else "pending"

        for index, item in enumerate(data):
            title = item.get("title")
            company_name = item.get("company")
            url = item.get("url", "No URL")
            
            if not title or not company_name:
                reason = "Missing job title or company name"
                skipped_details.append({"row": index, "title": title or "Unknown", "company": company_name or "Unknown", "reason": reason, "url": url})
                skipped += 1
                continue
            
            # Simple deduplication check
            if Job.objects.filter(title__iexact=title, company_obj__name__iexact=company_name).exists():
                reason = f"Job '{title}' at '{company_name}' already exists"
                skipped_details.append({"row": index, "title": title, "company": company_name, "reason": reason, "url": url})
                skipped += 1
                continue
                
            serializer = self.get_serializer(data=item)
            if serializer.is_valid():
                serializer.save(status=default_status, submittedBy=submitted_by)
                added += 1
            else:
                err_msg = str(serializer.errors)
                errors.append({"row": index, "title": title, "company": company_name, "error": err_msg, "url": url})
                skipped += 1

        return Response({
            "added": added,
            "skipped": skipped,
            "skipped_details": skipped_details,
            "errors": errors
        })


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


class UserListView(generics.ListAPIView):
    """Admin only: list all users, with pagination and filtering by status."""
    serializer_class = PendingUserSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["username", "email"]
    filterset_fields = ["status"]

    def get_queryset(self):
        return PendingUser.objects.all().order_by("-requestedAt")


class SalaryAggregateView(generics.ListAPIView):
    """Calculates aggregated salaries across all active jobs. Supports ?search query."""
    permission_classes = [AllowAny]
    
    def list(self, request, *args, **kwargs):
        import re
        jobs = Job.objects.filter(status="approved").exclude(salary__isnull=True).exclude(salary="")
        search_query = request.query_params.get("search", "").lower()

        title_map = {}
        for job in jobs:
            if search_query and search_query not in job.title.lower():
                continue

            # Basic parsing of "$100k - $120k" or similar strings
            salary_str = str(job.salary).lower().replace(",", "")
            numbers = [int(n) for n in re.findall(r"\d+", salary_str)]
            if not numbers:
                continue

            multiplier = 1000 if "k" in salary_str else 1
            parsed_nums = []
            for n in numbers:
                val = n * 1000 if (n < 1000 and multiplier == 1) else n * multiplier
                parsed_nums.append(val)

            avg_val = parsed_nums[0]
            if len(parsed_nums) == 1:
                parsed = {"min": parsed_nums[0], "max": parsed_nums[0], "avg": avg_val}
            elif len(parsed_nums) >= 2:
                avg_val = (parsed_nums[0] + parsed_nums[1]) / 2
                parsed = {"min": parsed_nums[0], "max": parsed_nums[1], "avg": avg_val}
            else:
                continue

            title = job.title.strip()
            if title not in title_map:
                title_map[title] = {
                    "title": title,
                    "jobCount": 0,
                    "minSalaries": [],
                    "maxSalaries": [],
                    "avgSalaries": [],
                    "companies": set()
                }

            title_map[title]["jobCount"] += 1
            title_map[title]["minSalaries"].append(parsed["min"])
            title_map[title]["maxSalaries"].append(parsed["max"])
            title_map[title]["avgSalaries"].append(parsed["avg"])
            
            if job.company_obj and hasattr(job.company_obj, "name"):
                title_map[title]["companies"].add(job.company_obj.name)

        results = []
        for item in title_map.values():
            avg_sum = sum(item["avgSalaries"])
            total_avg = avg_sum / len(item["avgSalaries"]) if item["avgSalaries"] else 0
            absolute_min = min(item["minSalaries"]) if item["minSalaries"] else 0
            absolute_max = max(item["maxSalaries"]) if item["maxSalaries"] else 0

            results.append({
                "title": item["title"],
                "jobCount": item["jobCount"],
                "topCompany": list(item["companies"])[0] if item["companies"] else "",
                "companies_count": len(item["companies"]),
                "totalAvg": total_avg,
                "absoluteMin": absolute_min,
                "absoluteMax": absolute_max
            })

        results.sort(key=lambda x: x["totalAvg"], reverse=True)

        page = self.paginate_queryset(results)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(results)
