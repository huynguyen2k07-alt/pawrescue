from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from organizations.models import RescueOrganization
from .models import CaseStatusHistory, Notification, RescueAssignment, RescueCase


@override_settings(SECURE_SSL_REDIRECT=False)
class CaseHandoffTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(email="handoff-admin@example.com", password="test-password")
        cls.reporter = users.objects.create_user(email="handoff-reporter@example.com", password="test-password")
        cls.operator = users.objects.create_user(
            email="handoff-operator@example.com", password="test-password", role=users.Role.COLLABORATOR,
        )
        cls.staff = users.objects.create_user(email="handoff-staff@example.com", password="test-password", is_staff=True)
        cls.partner = RescueOrganization.objects.create(
            name="Đơn vị cứu hộ kiểm thử", phone="0900000001", email="rescue@example.com", is_verified=True,
        )
        cls.case = RescueCase.objects.create(
            title="Yêu cầu cần chuyển đơn vị", animal_type="cat", description="Mèo bị thương cần hỗ trợ.",
            address="123 Nguyễn Văn Linh, Đà Nẵng", latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            reporter=cls.reporter, contact_name="Người báo tin", contact_phone="0900000002", is_location_private=True,
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse("rescue:case-handoff", args=(self.case.pk,))
        self.detail = reverse("rescue:case-detail", args=(self.case.pk,))

    def handoff(self, partner=None):
        return self.client.post(self.url, {"organization": (partner or self.partner).pk})

    def test_one_click_acceptance_uses_system_unit_and_notifies_once(self):
        url = reverse("rescue:case-claim", args=(self.case.pk,))
        self.assertRedirects(self.client.post(url), self.detail)
        self.case.refresh_from_db()
        self.assertTrue(self.case.organization.is_system)
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.assertEqual(self.case.status_history.count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.reporter).count(), 1)
        self.client.post(url)
        self.assertEqual(self.case.status_history.count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.reporter).count(), 1)

    def test_handoff_needs_no_partner_account_and_preserves_report(self):
        self.assertFalse(self.partner.memberships.exists())
        self.assertRedirects(self.handoff(), self.detail)
        self.case.refresh_from_db()
        self.assertEqual(self.case.organization, self.partner)
        self.assertEqual(self.case.status, RescueCase.Status.ASSIGNED)
        self.assertIsNone(self.case.closed_at)
        self.assertEqual(self.case.reporter, self.reporter)
        self.assertEqual(self.case.address, "123 Nguyễn Văn Linh, Đà Nẵng")
        history = self.case.status_history.get()
        self.assertEqual(history.changed_by, self.admin)
        self.assertIn(self.partner.name, history.note)
        self.assertTrue(Notification.objects.filter(recipient=self.reporter, kind=Notification.Kind.CASE_ASSIGNED).exists())

    def test_repeat_handoff_has_no_duplicate_history_or_notifications(self):
        self.handoff()
        histories = self.case.status_history.count()
        notifications = Notification.objects.count()
        self.handoff()
        self.assertEqual(self.case.status_history.count(), histories)
        self.assertEqual(Notification.objects.count(), notifications)

    def test_handoff_ends_previous_assignment_and_revokes_private_access(self):
        assignment = RescueAssignment.objects.create(rescue_case=self.case, assignee=self.operator, assigned_by=self.admin)
        operator = Client()
        operator.force_login(self.operator)
        self.assertTrue(operator.get(self.detail).context["can_view_location"])
        self.handoff()
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertIsNotNone(assignment.completed_at)
        self.assertFalse(operator.get(self.detail).context["can_view_location"])
        self.assertEqual(operator.get(reverse("rescue:case-messages", args=(self.case.pk,))).status_code, 404)

    def test_handoff_rejects_inactive_unverified_system_and_contactless_units(self):
        organizations = [
            RescueOrganization.objects.create(name="Chưa xác minh", phone="0900000003"),
            RescueOrganization.objects.create(name="Ngừng hoạt động", phone="0900000004", is_active=False, is_verified=True),
            RescueOrganization.objects.create(name="Thiếu liên hệ", is_verified=True),
            RescueOrganization.objects.get(is_system=True),
        ]
        for organization in organizations:
            with self.subTest(organization=organization.name):
                self.handoff(organization)
                self.case.refresh_from_db()
                self.assertIsNone(self.case.organization_id)
                self.assertEqual(self.case.status, RescueCase.Status.REPORTED)
        self.assertFalse(self.case.status_history.exists())

    def test_handoff_is_admin_post_only_and_enforces_csrf(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        for user in (self.reporter, self.operator, self.staff):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertEqual(self.handoff().status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(self.url, {"organization": self.partner.pk}).status_code, 403)
        self.case.refresh_from_db()
        self.assertIsNone(self.case.organization_id)

    def test_closed_case_cannot_be_handed_off(self):
        self.case.change_status(RescueCase.Status.RESCUED, changed_by=self.admin, note="Đã xử lý thành công.")
        self.handoff()
        self.case.refresh_from_db()
        self.assertIsNone(self.case.organization_id)
        self.assertEqual(self.case.status, RescueCase.Status.RESCUED)
        self.assertEqual(self.case.status_history.count(), 1)

    def test_email_handoff_is_a_draft_and_not_exposed_to_other_members(self):
        self.handoff()
        response = self.client.get(self.detail)
        link = response.context["handoff_email_url"]
        self.assertTrue(link.startswith("mailto:rescue@example.com?"))
        draft = parse_qs(urlsplit(link).query)
        self.assertIn(self.case.address, draft["body"][0])
        self.assertIn(self.case.contact_phone, draft["body"][0])
        outsider = get_user_model().objects.create_user(email="handoff-outsider@example.com", password="test-password")
        self.client.force_login(outsider)
        response = self.client.get(self.detail)
        self.assertEqual(response.context["handoff_email_url"], "")
        self.assertNotContains(response, self.case.address)

    def test_admin_keeps_final_review_and_can_delete_completed_request(self):
        self.handoff()
        final_url = reverse("rescue:case-update-status", args=(self.case.pk,))
        self.client.post(final_url, {"status": "rescued", "note": "Đơn vị đã xác nhận cứu hộ thành công."})
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.RESCUED)
        self.assertIsNotNone(self.case.closed_at)
        self.assertRedirects(self.client.post(reverse("admin:rescue_rescuecase_delete", args=(self.case.pk,)), {"post": "yes"}), reverse("admin:rescue_rescuecase_changelist"))
        self.assertFalse(RescueCase.objects.filter(pk=self.case.pk).exists())

    def test_admin_change_opens_workspace_and_explicit_edit_stays_available(self):
        url = reverse("admin:rescue_rescuecase_change", args=(self.case.pk,))
        self.assertRedirects(self.client.get(url), self.detail)
        response = self.client.get(url + "?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tiêu đề yêu cầu")
        self.assertNotContains(response, 'name="_addanother"')
        self.assertNotContains(response, 'name="_continue"')
        self.assertEqual(list(response.context["adminform"].form.fields).count("status"), 0)

    def test_admin_edit_does_not_reassign_reporter_or_unit(self):
        self.handoff()
        data = {
            "title": "Tiêu đề đã sửa", "description": self.case.description, "animal_type": "cat", "urgency": "medium",
            "address": self.case.address, "latitude": "16.054407", "longitude": "108.202167",
            "contact_name": self.case.contact_name, "contact_phone": self.case.contact_phone,
            "is_location_private": "on", "reporter": self.operator.pk, "organization": "",
            "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0", "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "1000", "_save": "1",
        }
        response = self.client.post(reverse("admin:rescue_rescuecase_change", args=(self.case.pk,)) + "?edit=1", data)
        self.assertRedirects(response, self.detail)
        self.case.refresh_from_db()
        self.assertEqual(self.case.title, "Tiêu đề đã sửa")
        self.assertEqual(self.case.reporter, self.reporter)
        self.assertEqual(self.case.organization, self.partner)
