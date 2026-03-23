from rest_framework import serializers

from .models import Company, Job, PendingUser, SubadminProfile


class SubadminProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = SubadminProfile
        fields = ["username", "displayName", "bio", "profileUrl", "avatarUrl"]
        read_only_fields = ["username"]


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = "__all__"
        read_only_fields = ["status", "submittedBy"]


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
