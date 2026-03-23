from django.contrib.auth.models import User
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)
    logoUrl = models.URLField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    website = models.URLField(max_length=500, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="pending",
    )
    submittedBy = models.CharField(max_length=150, blank=True, default="")

    def __str__(self):
        return self.name


class Job(models.Model):
    title = models.CharField(max_length=255)
    company_obj = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs")
    location = models.CharField(max_length=255)
    locationType = models.CharField(
        max_length=50,
        choices=[
            ("Remote", "Remote"),
            ("On-site", "On-site"),
            ("Hybrid", "Hybrid"),
        ],
        default="Remote",
    )
    jobType = models.CharField(
        max_length=50,
        choices=[
            ("Full-time", "Full-time"),
            ("Part-time", "Part-time"),
            ("Contract", "Contract"),
            ("Freelance", "Freelance"),
        ],
        default="Full-time",
    )
    salary = models.CharField(max_length=100)
    tags = models.JSONField(default=list)
    description = models.TextField()
    requirements = models.JSONField(default=list)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("pending_deletion", "Pending Deletion"),
        ],
        default="approved",
    )
    submittedBy = models.CharField(max_length=150, blank=True, default="")
    postedAt = models.DateTimeField(auto_now_add=True)
    expiryDate = models.DateTimeField(null=True, blank=True)
    apply_url = models.URLField(max_length=500, blank=True, default="")
    currency = models.CharField(
        max_length=10,
        choices=[
            ("USD", "USD ($)"),
            ("EUR", "EUR (€)"),
            ("GBP", "GBP (£)"),
            ("INR", "INR (₹)"),
        ],
        default="INR",
    )

    def __str__(self):
        return f"{self.title} at {self.company}"


class PendingUser(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("revoked", "Revoked"),
    ]
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)  # stored as hashed
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    requestedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.status})"


class SubadminProfile(models.Model):
    """Extended profile info for subadmin users — shown on job detail pages."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subadmin_profile")
    displayName = models.CharField(max_length=150, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    profileUrl = models.URLField(max_length=500, blank=True, default="", help_text="LinkedIn, GitHub, portfolio, etc.")
    avatarUrl = models.URLField(max_length=500, blank=True, default="")

    def __str__(self):
        return f"Profile: {self.user.username}"
