from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from requests_app.models import Category, ServiceRequest, WorkOrder
from requests_app.services import service_request_resolve


class ServiceRequestCrudTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("owner", password="pass12345")
        self.other = User.objects.create_user("other", password="pass12345")
        self.staff = User.objects.create_user("tech_staff", password="pass12345", is_staff=True)
        self.category = Category.objects.create(name="Facilities")
        self.item = ServiceRequest.objects.create(
            requester=self.owner,
            category=self.category,
            title="Projector does not display",
            description="The projector reports no HDMI signal.",
            location="Room B12",
            priority=3,
        )

    def test_list_requires_login(self):
        response = self.client.get(reverse("requests:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_owner_can_open_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.item.title)

    def test_other_requester_receives_404(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("requests:detail", args=[self.item.id]))
        self.assertEqual(response.status_code, 404)

    def test_valid_post_creates_request_for_logged_in_user(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("requests:create"),
            {
                "category": self.category.id,
                "title": "Air conditioner leaks water",
                "description": "Water drips near the laboratory entrance.",
                "location": "Software Laboratory",
                "priority": 1,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ServiceRequest.objects.filter(
                requester=self.owner, title="Air conditioner leaks water"
            ).exists()
        )

    def test_invalid_post_does_not_create_request(self):
        self.client.force_login(self.owner)
        before = ServiceRequest.objects.count()
        response = self.client.post(
            reverse("requests:create"),
            {
                "category": self.category.id,
                "title": "Short",
                "description": "",
                "location": "",
                "priority": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ServiceRequest.objects.count(), before)
        self.assertContains(response, "Use at least 8 characters.")

    def test_non_staff_assignment_returns_403_and_creates_no_work_order(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("requests:assign", args=[self.item.id]),
            {"technician": self.staff.id},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(WorkOrder.objects.filter(service_request=self.item).exists())

    def test_staff_assignment_creates_work_order_and_sets_assigned(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("requests:assign", args=[self.item.id]),
            {"technician": self.staff.id},
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ServiceRequest.Status.ASSIGNED)
        self.assertEqual(WorkOrder.objects.filter(service_request=self.item).count(), 1)

    def test_resolution_without_assignment_leaves_request_unchanged(self):
        with self.assertRaises(ValidationError):
            service_request_resolve(
                item=self.item,
                actor=self.staff,
                work_notes="Attempted resolution without assignment.",
            )
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, ServiceRequest.Status.OPEN)
        self.assertIsNone(self.item.resolved_at)

    def test_assigned_technician_resolution_updates_both_models(self):
        WorkOrder.objects.create(service_request=self.item, technician=self.staff)
        self.item.status = ServiceRequest.Status.ASSIGNED
        self.item.save(update_fields=["status", "updated_at"])

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("requests:resolve", args=[self.item.id]),
            {"work_notes": "Replaced faulty HDMI cable and tested projector."},
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        work_order = WorkOrder.objects.get(service_request=self.item)
        self.assertEqual(self.item.status, ServiceRequest.Status.RESOLVED)
        self.assertIsNotNone(self.item.resolved_at)
        self.assertIsNotNone(work_order.completed_at)
        self.assertEqual(
            work_order.work_notes,
            "Replaced faulty HDMI cable and tested projector.",
        )

    def test_filtered_pagination_preserves_q_and_status(self):
        for i in range(12):
            ServiceRequest.objects.create(
                requester=self.owner,
                category=self.category,
                title=f"Network switch port {i + 1}",
                description="Switch port flapping.",
                location="Lab C",
                priority=2,
                status=ServiceRequest.Status.OPEN,
            )

        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("requests:list"),
            {"q": "Network", "status": "open", "page": 2},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Network"')
        self.assertContains(response, '<option value="open" selected>Open</option>', html=True)
        self.assertContains(response, "q=Network")
        self.assertContains(response, "status=open")
