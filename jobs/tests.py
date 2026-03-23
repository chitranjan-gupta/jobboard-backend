from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Company, Job


class CompanyAPITests(APITestCase):
    def setUp(self):
        # Create users
        self.admin_user = User.objects.create_superuser("admin", "admin@example.com", "pass123")
        self.subadmin_user = User.objects.create_user("subadmin", "subadmin@example.com", "pass123")

        # Create some companies
        self.approved_company = Company.objects.create(name="Approved Corp", status="approved", submittedBy="admin")
        self.pending_company = Company.objects.create(name="Pending Corp", status="pending", submittedBy="subadmin")
        self.rejected_company = Company.objects.create(name="Rejected Corp", status="rejected", submittedBy="subadmin")

        self.companies_url = "/api/companies/"
        self.pending_companies_url = "/api/companies/pending/"

    def test_list_approved_companies_public(self):
        """Public users should only see approved companies."""
        response = self.client.get(self.companies_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should only return approved_company
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Approved Corp")

    def test_create_company_as_subadmin(self):
        """Subadmins can create companies, but they default to pending."""
        self.client.force_authenticate(user=self.subadmin_user)
        data = {"name": "New Subadmin Corp", "description": "Test"}
        response = self.client.post(self.companies_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["submittedBy"], "subadmin")

    def test_create_company_as_admin(self):
        """Admins can create companies, and they are automatically approved."""
        self.client.force_authenticate(user=self.admin_user)
        data = {"name": "New Admin Corp", "description": "Test"}
        response = self.client.post(self.companies_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "approved")
        self.assertEqual(response.data["submittedBy"], "admin")

    def test_list_pending_companies_as_admin(self):
        """Admins can view pending companies."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.pending_companies_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Assuming pending_companies_url returns all non-approved (pending and rejected)
        # Actually in views.py it returns status='pending'. Let's verify:
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Pending Corp")

    def test_list_pending_companies_as_subadmin(self):
        """Subadmins cannot view the pending companies list endpoint."""
        self.client.force_authenticate(user=self.subadmin_user)
        response = self.client.get(self.pending_companies_url)
        # Should be forbidden because it's IsAdminUser
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approve_company_as_admin(self):
        """Admins can approve a pending company."""
        self.client.force_authenticate(user=self.admin_user)
        approve_url = f"/api/companies/{self.pending_company.id}/approve/"
        response = self.client.post(approve_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_company.refresh_from_db()
        self.assertEqual(self.pending_company.status, "approved")

    def test_reject_company_as_admin(self):
        """Admins can reject a pending company."""
        self.client.force_authenticate(user=self.admin_user)
        reject_url = f"/api/companies/{self.pending_company.id}/reject/"
        response = self.client.post(reject_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_company.refresh_from_db()
        self.assertEqual(self.pending_company.status, "rejected")

    def test_subadmin_list_includes_their_pending(self):
        """Subadmins should see approved + their own pending/rejected in the main list."""
        self.client.force_authenticate(user=self.subadmin_user)
        response = self.client.get(self.companies_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Approved Corp, Pending Corp (subadmin), Rejected Corp (subadmin)
        names = [c["name"] for c in response.data]
        self.assertEqual(len(names), 3)
        self.assertIn("Approved Corp", names)
        self.assertIn("Pending Corp", names)
        self.assertIn("Rejected Corp", names)

    def test_update_approved_company_as_subadmin_reverts_to_pending(self):
        """If a subadmin edits an approved company, it should revert to pending."""
        self.client.force_authenticate(user=self.subadmin_user)
        update_url = f"/api/companies/{self.approved_company.id}/"
        data = {"name": "Approved Corp Updated"}
        response = self.client.patch(update_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.approved_company.refresh_from_db()
        self.assertEqual(self.approved_company.name, "Approved Corp Updated")
        self.assertEqual(self.approved_company.status, "pending")


class JobAPITests(APITestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser("admin2", "admin2@example.com", "pass123")
        self.subadmin_user = User.objects.create_user("subadmin2", "subadmin2@example.com", "pass123")

        self.approved_company = Company.objects.create(name="Job Company", status="approved", submittedBy="admin2")

        self.approved_job = Job.objects.create(
            company_obj=self.approved_company,
            title="Approved Engineer",
            jobType="Full-time",
            location="Remote",
            salary="100000",
            tags=["React"],
            status="approved",
            submittedBy="admin2",
            currency="USD",
            description="Testing",
        )
        self.pending_job = Job.objects.create(
            company_obj=self.approved_company,
            title="Pending Engineer",
            jobType="Part-time",
            location="On-site",
            salary="80000",
            tags=["Python"],
            status="pending",
            submittedBy="subadmin2",
            description="Testing",
        )
        self.deletion_job = Job.objects.create(
            company_obj=self.approved_company,
            title="To Be Deleted",
            jobType="Contract",
            location="Remote",
            salary="120000",
            tags=["Node"],
            status="pending_deletion",
            submittedBy="subadmin2",
            description="Testing",
        )
        self.jobs_url = "/api/jobs/"

    def test_list_approved_jobs_public(self):
        """Public users should only see approved jobs."""
        response = self.client.get(self.jobs_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Assuming pagination or flat list, let's just check length if unpaginated or results if paginated
        data = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Approved Engineer")

    def test_create_job_as_subadmin(self):
        """Subadmins can create jobs, but they default to pending."""
        self.client.force_authenticate(user=self.subadmin_user)
        data = {
            "companyId": self.approved_company.id,
            "title": "New Subadmin Job",
            "jobType": "Full-time",
            "location": "Remote",
            "salary": "90000",
            "description": "Testing",
            "currency": "USD",
        }
        response = self.client.post(self.jobs_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["submittedBy"], "subadmin2")

    def test_approve_job_as_admin(self):
        """Admins can approve a pending job."""
        self.client.force_authenticate(user=self.admin_user)
        approve_url = f"/api/jobs/{self.pending_job.id}/approve/"
        response = self.client.post(approve_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_job.refresh_from_db()
        self.assertEqual(self.pending_job.status, "approved")

    def test_request_delete_job_as_subadmin(self):
        """Subadmins can request deletion of an approved job they created."""

        # We need an approved job that was submitted by subadmin2
        self.subadmin_approved_job = Job.objects.create(
            company_obj=self.approved_company,
            title="Subadmin Approved Engineer",
            status="approved",
            submittedBy="subadmin2",
        )
        self.client.force_authenticate(user=self.subadmin_user)
        request_url = f"/api/jobs/{self.subadmin_approved_job.id}/request_delete/"
        response = self.client.post(request_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.subadmin_approved_job.refresh_from_db()
        self.assertEqual(self.subadmin_approved_job.status, "pending_deletion")

    def test_approve_deletion_as_admin(self):
        """Admins can approve a deletion request, which deletes the job."""
        self.client.force_authenticate(user=self.admin_user)
        self.assertEqual(Job.objects.filter(id=self.deletion_job.id).exists(), True)
        delete_url = f"/api/jobs/{self.deletion_job.id}/approve_deletion/"
        response = self.client.post(delete_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Job.objects.filter(id=self.deletion_job.id).exists(), False)
