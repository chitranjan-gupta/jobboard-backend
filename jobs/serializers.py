from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed

from .models import Company, Job, PendingUser, SubadminProfile

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        username = attrs.get(self.username_field)
        password = attrs.get('password')

        if username and password:
            from django.contrib.auth.models import User
            from django.contrib.auth.hashers import check_password
            from .models import PendingUser

            user = User.objects.filter(username=username).first()
            if user:
                if user.check_password(password):
                    if not user.is_active:
                        pending_user = PendingUser.objects.filter(username=username).first()
                        if pending_user:
                            if pending_user.status == 'revoked':
                                raise AuthenticationFailed("Your access is revoked.", code="user_revoked")
                            if pending_user.status == 'pending':
                                raise AuthenticationFailed("Your account is pending approval.", code="user_pending")
            else:
                # Check PendingUser if no Django User exists (could be correct credentials but not yet approved)
                pending_user = PendingUser.objects.filter(username=username).first()
                if pending_user and check_password(password, pending_user.password):
                    if pending_user.status == 'pending':
                        raise AuthenticationFailed("access is pending from admin", code="user_pending")
                    if pending_user.status == 'rejected':
                        raise AuthenticationFailed("Your registration request was rejected.", code="user_rejected")
                    
        return super().validate(attrs)


class SubadminProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = SubadminProfile
        fields = ["username", "displayName", "bio", "profileUrl", "avatarUrl"]
        read_only_fields = ["username"]


class CompanySerializer(serializers.ModelSerializer):
    job_count = serializers.IntegerField(read_only=True)
    location_types = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "logoUrl",
            "description",
            "website",
            "status",
            "submittedBy",
            "job_count",
            "location_types",
        ]
        read_only_fields = ["status", "submittedBy", "job_count", "location_types"]

    def get_location_types(self, obj):
        # We only want to show location types for APPROVED jobs
        return list(obj.jobs.filter(status="approved").values_list("locationType", flat=True).distinct())


class JobSerializer(serializers.ModelSerializer):
    companyId = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all(), source="company_obj")
    company = serializers.CharField(source="company_obj.name", read_only=True)
    companyLogo = serializers.URLField(source="company_obj.logoUrl", read_only=True)
    aboutCompany = serializers.CharField(source="company_obj.description", read_only=True)

    # Inline poster profile — null when no profile exists
    posterProfile = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "title",
            "companyId",
            "company",
            "companyLogo",
            "aboutCompany",
            "location",
            "locationType",
            "jobType",
            "salary",
            "currency",
            "tags",
            "description",
            "requirements",
            "status",
            "submittedBy",
            "postedAt",
            "expiryDate",
            "apply_url",
            "posterProfile",
        ]
        read_only_fields = ["status", "submittedBy", "postedAt"]
        extra_kwargs = {"company_obj": {"required": False, "allow_null": True}}

    def get_posterProfile(self, obj):
        if not obj.submittedBy:
            return None
        from django.contrib.auth.models import User

        try:
            user = User.objects.get(username=obj.submittedBy)
            profile, _ = SubadminProfile.objects.get_or_create(user=user)
            return SubadminProfileSerializer(profile).data
        except User.DoesNotExist:
            return None


class PendingUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingUser
        fields = ["id", "username", "email", "status", "requestedAt"]
        read_only_fields = ["status", "requestedAt"]
