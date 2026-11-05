"""Kiểm tra quản trị viên xử lý ca được giao, còn admin chính duyệt kết quả."""

from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Notification, RescueAssignment, RescueCase, RescueCaseMessage


@override_settings(SECURE_SSL_REDIRECT=False)
class ModeratorWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="workflow-main-admin@example.com", password="test-password",
        )
        cls.moderator = users.objects.create_user(
            email="workflow-moderator@example.com", password="test-password",
            role=users.Role.MODERATOR,
        )
        cls.other_moderator = users.objects.create_user(
            email="workflow-other-moderator@example.com", password="test-password",
            role=users.Role.MODERATOR,
        )
        cls.reporter = users.objects.create_user(
            email="workflow-reporter@example.com", password="test-password",
        )
        cls.operator = users.objects.create_user(
            email="workflow-operator@example.com", password="test-password",
            role=users.Role.COLLABORATOR,
        )
        cls.case = RescueCase.objects.create(
            title="Tin báo riêng cần quản trị viên kiểm tra", description="Mèo bị thương ở hiện trường.",
            animal_type=RescueCase.AnimalType.CAT, reporter=cls.reporter,
            address="157 Nguyễn Văn Linh, Hải Châu, Đà Nẵng",
            latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            is_location_private=True, contact_phone="0901234567",
        )
        cls.assignment = RescueAssignment.objects.create(
            rescue_case=cls.case, assignee=cls.moderator, assigned_by=cls.admin,
        )

    def setUp(self):
        self.client.force_login(self.moderator)

    def detail_url(self):
        return reverse("rescue:case-detail", args=(self.case.pk,))

    def status_url(self):
        return reverse("rescue:case-update-status", args=(self.case.pk,))

    def reject_url(self):
        return reverse("rescue:case-reject", args=(self.case.pk,))

    def set_status(self, status):
        RescueCase.objects.filter(pk=self.case.pk).update(status=status)
        self.case.refresh_from_db()

    def post_status(self, status, note="Đã kiểm tra và xác nhận thông tin."):
        return self.client.post(self.status_url(), {"status": status, "note": note})

    def test_assigned_moderator_can_verify_reported_or_assigned_case(self):
        for previous in (RescueCase.Status.REPORTED, RescueCase.Status.ASSIGNED):
            with self.subTest(previous=previous):
                self.set_status(previous)
                response = self.post_status(RescueCase.Status.VERIFIED)
                self.assertRedirects(response, self.detail_url())
                self.case.refresh_from_db()
                self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
                history = self.case.status_history.first()
                self.assertEqual(history.changed_by, self.moderator)
                self.assertEqual(history.from_status, previous)
                self.assertEqual(history.to_status, RescueCase.Status.VERIFIED)
                self.assertIsNone(self.case.closed_at)

    def test_unassigned_or_revoked_moderator_cannot_change_status(self):
        self.client.force_login(self.other_moderator)
        self.assertIn(self.post_status(RescueCase.Status.VERIFIED).status_code, (403, 404))
        self.assignment.is_active = False
        self.assignment.save(update_fields=("is_active",))
        self.client.force_login(self.moderator)
        self.assertIn(self.post_status(RescueCase.Status.VERIFIED).status_code, (403, 404))
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.REPORTED)
        self.assertFalse(self.case.status_history.exists())

    def test_moderator_cannot_finalize_or_dispatch_case(self):
        self.set_status(RescueCase.Status.VERIFIED)
        for status in (RescueCase.Status.RESCUED, RescueCase.Status.CLOSED, RescueCase.Status.CANCELLED):
            with self.subTest(status=status):
                self.assertEqual(self.post_status(status).status_code, 403)
        for name, payload in (
            ("case-notify-admins", {}), ("case-claim", {}),
            ("case-assign", {"assignee": self.other_moderator.pk}), ("case-handoff", {}),
        ):
            with self.subTest(action=name):
                response = self.client.post(reverse(f"rescue:{name}", args=(self.case.pk,)), payload)
                self.assertEqual(response.status_code, 403)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.assertFalse(self.case.status_history.exists())
        self.assertEqual(self.case.assignments.count(), 1)

    def test_reporter_and_regular_assignee_cannot_use_moderator_status_actions(self):
        RescueAssignment.objects.create(
            rescue_case=self.case, assignee=self.operator, assigned_by=self.admin,
        )
        for user in (self.reporter, self.operator):
            self.client.force_login(user)
            for status in (RescueCase.Status.VERIFIED, RescueCase.Status.PENDING_REVIEW):
                with self.subTest(user=user.email, status=status):
                    self.assertEqual(self.post_status(status).status_code, 403)
        self.assertFalse(self.case.status_history.exists())

    def test_pending_result_requires_verification_evaluation_and_valid_location(self):
        self.post_status(RescueCase.Status.PENDING_REVIEW, "Đã cứu xong nhưng chưa kiểm tra tin báo.")
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.REPORTED)
        self.set_status(RescueCase.Status.VERIFIED)
        for note in ("", "   "):
            with self.subTest(note=note):
                self.post_status(RescueCase.Status.PENDING_REVIEW, note)
                self.case.refresh_from_db()
                self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.case.longitude = None
        self.case.save(update_fields=("longitude",))
        self.post_status(RescueCase.Status.PENDING_REVIEW, "Đã hoàn tất ngoài hiện trường.")
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.assertFalse(self.case.status_history.exists())

    def test_moderator_completion_records_author_note_and_waits_for_main_admin(self):
        self.set_status(RescueCase.Status.VERIFIED)
        note = "Đã bàn giao mèo an toàn cho cơ sở thú y, chờ admin duyệt ảnh kết quả."
        response = self.post_status(RescueCase.Status.PENDING_REVIEW, note)
        self.assertRedirects(response, self.detail_url())
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.PENDING_REVIEW)
        self.assertIsNone(self.case.closed_at)
        history = self.case.status_history.get()
        self.assertEqual(history.changed_by, self.moderator)
        self.assertEqual(history.note, note)
        self.assertIsNotNone(history.changed_at)
        self.assertTrue(self.case.notifications.filter(recipient=self.admin).exists())
        markers = Client().get(reverse("rescue:case-map")).context["map_cases"]
        self.assertNotIn(self.case.pk, [marker["id"] for marker in markers])

    def test_only_main_admin_approval_publishes_completed_case(self):
        self.set_status(RescueCase.Status.VERIFIED)
        self.post_status(RescueCase.Status.PENDING_REVIEW, "Đã hoàn thành cứu hộ và kiểm tra hiện trường.")
        original_location = (self.case.address, self.case.latitude, self.case.longitude)
        self.client.force_login(self.admin)
        response = self.post_status(RescueCase.Status.RESCUED, "Admin đã xem kết quả, duyệt cứu hộ thành công.")
        self.assertRedirects(response, self.detail_url())
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.RESCUED)
        self.assertIsNotNone(self.case.closed_at)
        self.assertEqual((self.case.address, self.case.latitude, self.case.longitude), original_location)
        self.assertEqual(self.case.status_history.count(), 2)
        history = self.case.status_history.first()
        self.assertEqual(history.changed_by, self.admin)
        self.assertEqual(history.from_status, RescueCase.Status.PENDING_REVIEW)
        markers = Client().get(reverse("rescue:case-map")).context["map_cases"]
        marker = next(item for item in markers if item["id"] == self.case.pk)
        self.assertTrue(marker["is_approximate"])
        self.assertTrue(marker["completed_at_display"])
        self.assertEqual(marker["detail_url"], self.detail_url())
        self.assertEqual(Client().get(marker["detail_url"]).status_code, 200)

    def test_pending_review_blocks_moderator_mutations_and_repeated_completion(self):
        self.set_status(RescueCase.Status.VERIFIED)
        self.post_status(RescueCase.Status.PENDING_REVIEW, "Đã hoàn tất và gửi duyệt.")
        notification_ids = set(self.case.notifications.values_list("pk", flat=True))
        for status in (RescueCase.Status.PENDING_REVIEW, RescueCase.Status.VERIFIED):
            self.post_status(status, "Thử sửa sau khi gửi duyệt.")
        self.client.post(reverse("rescue:case-add-update", args=(self.case.pk,)), {"note": "Cập nhật muộn."})
        self.client.post(self.reject_url(), {"confirm": "yes", "reason": "Không được xóa khi chờ duyệt."})
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.PENDING_REVIEW)
        self.assertEqual(self.case.status_history.count(), 1)
        self.assertFalse(self.case.updates.exists())
        self.assertEqual(set(self.case.notifications.values_list("pk", flat=True)), notification_ids)

    def test_reject_get_only_shows_confirmation_and_invalid_post_preserves_case(self):
        response = self.client.get(self.reject_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.case.title)
        self.assertTrue(RescueCase.objects.filter(pk=self.case.pk).exists())
        for payload in ({}, {"confirm": "yes"}, {"confirm": "yes", "reason": "   "}, {"reason": "Tin báo sai."}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.reject_url(), payload).status_code, 400)
                self.assertTrue(RescueCase.objects.filter(pk=self.case.pk).exists())
        self.assertFalse(self.case.notifications.exists())

    def test_confirmed_rejection_deletes_case_and_keeps_notifications_for_reporter_and_admin(self):
        RescueCaseMessage.objects.create(
            rescue_case=self.case, sender=self.admin, recipient=self.moderator,
            body="Thông tin điều phối sẽ được xóa cùng tin báo bị từ chối.",
        )
        case_id = self.case.pk
        reason = "Đã kiểm tra hiện trường, đây là tin trùng lặp."
        response = self.client.post(self.reject_url(), {"confirm": "yes", "reason": reason})
        self.assertRedirects(response, reverse("collaborators:dashboard"))
        self.assertFalse(RescueCase.objects.filter(pk=case_id).exists())
        self.assertFalse(RescueAssignment.objects.filter(rescue_case_id=case_id).exists())
        self.assertFalse(RescueCaseMessage.objects.filter(rescue_case_id=case_id).exists())
        notifications = Notification.objects.filter(actor=self.moderator)
        self.assertEqual(set(notifications.values_list("recipient_id", flat=True)), {
            self.admin.pk, self.reporter.pk,
        })
        self.assertTrue(all(item.rescue_case_id is None for item in notifications))
        for item in notifications:
            self.assertIn(reason, item.message)
            self.assertIn(self.case.title, item.message)
        markers = Client().get(reverse("rescue:case-map")).context["map_cases"]
        self.assertNotIn(case_id, [marker["id"] for marker in markers])

    def test_rejection_rejects_unassigned_users_and_enforces_csrf(self):
        for user in (self.reporter, self.operator, self.other_moderator):
            with self.subTest(user=user.email):
                client = Client()
                client.force_login(user)
                response = client.post(self.reject_url(), {"confirm": "yes", "reason": "Không được quyền xóa."})
                self.assertIn(response.status_code, (403, 404))
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.moderator)
        self.assertEqual(csrf_client.post(self.reject_url(), {
            "confirm": "yes", "reason": "Thiếu CSRF.",
        }).status_code, 403)
        self.assertTrue(RescueCase.objects.filter(pk=self.case.pk).exists())

    def test_finalized_or_pending_cases_cannot_be_rejected(self):
        for status in (RescueCase.Status.PENDING_REVIEW, RescueCase.Status.RESCUED,
                       RescueCase.Status.CLOSED, RescueCase.Status.CANCELLED):
            with self.subTest(status=status):
                self.set_status(status)
                self.client.post(self.reject_url(), {"confirm": "yes", "reason": "Thử xóa hồ sơ đã chốt."})
                self.case.refresh_from_db()
                self.assertEqual(self.case.status, status)
        self.assertFalse(self.case.notifications.exists())

    def test_moderator_workspace_has_review_actions_without_global_admin_controls(self):
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_manage"])
        self.assertTrue(response.context["can_review"])
        self.assertContains(response, 'id="moderator-actions"')
        self.assertContains(response, "Xác nhận thông tin")
        self.assertContains(response, self.reject_url())
        for name in ("case-notify-admins", "case-assign", "case-handoff"):
            self.assertNotContains(response, f'action="{reverse(f"rescue:{name}", args=(self.case.pk,))}"')
        self.assertNotContains(response, reverse("admin:rescue_rescuecase_delete", args=(self.case.pk,)))
        self.assertNotContains(response, 'name="status" value="rescued"')

    def test_google_maps_link_uses_viewer_visible_coordinates_and_escaped_parameters(self):
        self.set_status(RescueCase.Status.VERIFIED)
        for user in (None, self.other_moderator, self.moderator, self.reporter, self.admin):
            with self.subTest(user=user.email if user else "guest"):
                client = Client()
                if user:
                    client.force_login(user)
                response = client.get(self.detail_url())
                url = response.context["google_maps_url"]
                parsed = urlsplit(url)
                self.assertEqual(parsed.hostname, "www.google.com")
                query = parse_qs(parsed.query)
                self.assertEqual(query["api"], ["1"])
                can_view_exact = user in (self.moderator, self.reporter, self.admin)
                latitude = float(self.case.latitude) if can_view_exact else round(float(self.case.latitude), 2)
                longitude = float(self.case.longitude) if can_view_exact else round(float(self.case.longitude), 2)
                coordinates = [float(value) for value in query["query"][0].split(",")]
                self.assertEqual(coordinates, [latitude, longitude])
                self.assertContains(response, url.replace("&", "&amp;"))
                self.assertContains(response, 'target="_blank" rel="noopener noreferrer"')
                if not can_view_exact:
                    self.assertNotContains(response, str(self.case.latitude))
                    self.assertNotContains(response, str(self.case.longitude))

    def test_broadcast_preserves_reported_state_until_assigned_moderator_verifies(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("rescue:case-notify-admins", args=(self.case.pk,)))
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.REPORTED)
        self.assertFalse(self.case.status_history.exists())
        self.assertTrue(self.case.assignments.filter(assignee=self.other_moderator, is_active=True).exists())
        self.client.force_login(self.other_moderator)
        self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        self.assertRedirects(self.post_status(RescueCase.Status.VERIFIED), self.detail_url())
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
