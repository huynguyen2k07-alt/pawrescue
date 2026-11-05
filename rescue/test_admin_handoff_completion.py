"""Kiểm thử gửi ca cho quản trị viên được phân công và chốt thành công lên bản đồ."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import (
    CaseStatusHistory,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseMessage,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminHandoffCompletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="handoff-complete-admin@example.com", password="test-password",
            full_name="Admin gửi ca",
        )
        cls.moderator = users.objects.create_user(
            email="handoff-complete-other@example.com", password="test-password",
            full_name="Quản trị viên nhận ca", role=users.Role.MODERATOR,
        )
        cls.other_moderator = users.objects.create_user(
            email="handoff-complete-third@example.com", password="test-password",
            role=users.Role.MODERATOR,
        )
        cls.inactive_admin = users.objects.create_superuser(
            email="handoff-complete-inactive@example.com", password="test-password",
            is_active=False,
        )
        cls.legacy_admin = users.objects.create_superuser(
            email="handoff-complete-legacy@example.com", password="test-password",
        )
        cls.inactive_moderator = users.objects.create_user(
            email="handoff-complete-inactive-moderator@example.com", password="test-password",
            role=users.Role.MODERATOR, is_active=False,
        )
        cls.reporter = users.objects.create_user(
            email="handoff-complete-reporter@example.com", password="test-password",
        )
        cls.operator = users.objects.create_user(
            email="handoff-complete-operator@example.com", password="test-password",
            role=users.Role.COLLABORATOR,
        )
        cls.staff = users.objects.create_user(
            email="handoff-complete-staff@example.com", password="test-password",
            is_staff=True,
        )
        cls.case = RescueCase.objects.create(
            title="Mèo bị thương cần điều phối và xác nhận",
            description="Cần mang lồng vận chuyển đến hiện trường.",
            animal_type=RescueCase.AnimalType.CAT,
            reporter=cls.reporter,
            status=RescueCase.Status.VERIFIED,
            address="157 Nguyễn Văn Linh, Hải Châu, Đà Nẵng",
            latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            contact_name="Người báo tin", contact_phone="0901234567",
            is_location_private=True,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def detail_url(self, case=None):
        return reverse("rescue:case-detail", args=((case or self.case).pk,))

    def notify_url(self, case=None):
        return reverse("rescue:case-notify-admins", args=((case or self.case).pk,))

    def message_url(self, case=None):
        return reverse("rescue:case-messages", args=((case or self.case).pk,))

    def complete(self, case=None, note="Đã kiểm tra kết quả, động vật đã an toàn."):
        return self.client.post(
            reverse("rescue:case-update-status", args=((case or self.case).pk,)),
            {"status": RescueCase.Status.RESCUED, "note": note},
        )

    def test_send_to_active_moderators_assigns_them_without_changing_case_status(self):
        response = self.client.post(self.notify_url(), {
            "recipient": self.staff.pk, "body": "Nội dung tùy ý không được dùng để gửi tự động.",
        })
        self.assertRedirects(response, self.detail_url())
        messages = self.case.private_messages.all()
        expected = {self.moderator.pk, self.other_moderator.pk}
        self.assertEqual(set(messages.values_list("recipient_id", flat=True)), expected)
        self.assertEqual(messages.count(), len(expected))
        for message in messages:
            self.assertEqual(message.sender, self.admin)
            self.assertIn(self.case.title, message.body)
            self.assertIn(self.case.address, message.body)
            self.assertIn(str(self.case.latitude), message.body)
            self.assertIn(str(self.case.longitude), message.body)
            self.assertIn(self.detail_url(), message.body)
            self.assertNotIn("Nội dung tùy ý", message.body)
            self.assertIsNone(message.read_at)
        notifications = self.case.notifications.all()
        self.assertEqual(set(notifications.values_list("recipient_id", flat=True)), expected)
        self.assertEqual(notifications.count(), len(expected))
        for notification in notifications:
            self.assertEqual(notification.actor, self.admin)
            self.assertEqual(notification.kind, Notification.Kind.CASE_MESSAGE)
            self.assertEqual(notification.target_url, self.message_url())
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.assertIsNone(self.case.closed_at)
        self.assertFalse(self.case.status_history.exists())
        self.assertEqual(set(self.case.assignments.values_list("assignee_id", flat=True)), expected)
        for assignment in self.case.assignments.all():
            self.assertEqual(assignment.assigned_by, self.admin)
            self.assertTrue(assignment.is_active)
            self.assertIsNone(assignment.completed_at)
            self.assertTrue(assignment.notes)

    def test_repeat_send_does_not_duplicate_messages_or_notifications(self):
        self.client.post(self.notify_url())
        original_ids = set(self.case.private_messages.values_list("pk", flat=True))
        original_notifications = set(self.case.notifications.values_list("pk", flat=True))
        original_assignments = set(self.case.assignments.values_list("pk", flat=True))
        self.client.post(self.notify_url())
        self.assertEqual(
            set(self.case.private_messages.values_list("pk", flat=True)), original_ids,
        )
        self.assertEqual(
            set(self.case.notifications.values_list("pk", flat=True)), original_notifications,
        )
        self.assertEqual(set(self.case.assignments.values_list("pk", flat=True)), original_assignments)

    def test_automatic_message_keeps_case_link_with_a_long_stored_address(self):
        self.case.title = "A" * 200
        self.case.address = "Địa chỉ hiện trường rất dài. " * 100
        self.case.save(update_fields=("title", "address"))
        self.client.post(self.notify_url())
        self.assertEqual(self.case.private_messages.count(), 2)
        for message in self.case.private_messages.all():
            self.assertLessEqual(len(message.body), 2000)
            self.assertIn(self.case.title, message.body)
            self.assertIn(self.case.address[:1200], message.body)
            self.assertIn(self.detail_url(), message.body)
            self.assertIn(str(self.case.latitude), message.body)
            self.assertIn(str(self.case.longitude), message.body)

    def test_send_after_a_new_moderator_is_added_only_delivers_to_the_new_recipient(self):
        self.client.post(self.notify_url())
        late_admin = get_user_model().objects.create_user(
            email="handoff-complete-new@example.com", password="test-password",
            role=get_user_model().Role.MODERATOR,
        )
        self.client.post(self.notify_url())
        self.assertEqual(self.case.private_messages.count(), 3)
        self.assertEqual(self.case.notifications.count(), 3)
        self.assertTrue(self.case.private_messages.filter(recipient=late_admin).exists())

    def test_broadcast_reactivates_existing_assignment_and_sends_one_fresh_notice(self):
        self.client.post(self.notify_url())
        assignment = self.case.assignments.get(assignee=self.moderator)
        original_id = assignment.pk
        assignment.is_active = False
        assignment.save(update_fields=("is_active",))
        self.client.post(self.notify_url())
        assignment.refresh_from_db()
        self.assertEqual(assignment.pk, original_id)
        self.assertTrue(assignment.is_active)
        self.assertIsNone(assignment.completed_at)
        self.assertEqual(assignment.assigned_by, self.admin)
        self.assertEqual(self.case.private_messages.filter(recipient=self.moderator).count(), 2)
        self.assertEqual(self.case.notifications.filter(recipient=self.moderator).count(), 2)
        self.client.post(self.notify_url())
        self.assertEqual(self.case.private_messages.count(), 3)
        self.assertEqual(self.case.notifications.count(), 3)

    def test_no_active_moderators_produces_no_messages_or_case_mutation(self):
        get_user_model().objects.filter(pk__in=(self.moderator.pk, self.other_moderator.pk)).update(
            is_active=False,
        )
        self.assertRedirects(self.client.post(self.notify_url()), self.detail_url())
        self.assertFalse(self.case.private_messages.exists())
        self.assertFalse(self.case.notifications.exists())
        self.assertFalse(self.case.assignments.exists())
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)

    def test_admin_handoff_is_post_only_requires_login_and_csrf(self):
        self.assertEqual(self.client.get(self.notify_url()).status_code, 405)
        anonymous = Client()
        response = anonymous.post(self.notify_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(self.notify_url()).status_code, 403)
        self.assertFalse(self.case.private_messages.exists())

    def test_reporter_operator_assignee_and_staff_cannot_broadcast_to_admins(self):
        RescueAssignment.objects.create(
            rescue_case=self.case, assignee=self.operator, assigned_by=self.admin,
        )
        for user in (self.reporter, self.operator, self.staff):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.post(self.notify_url(), {"recipient": self.moderator.pk})
                self.assertEqual(response.status_code, 403)
        self.assertFalse(self.case.private_messages.exists())
        self.assertFalse(self.case.notifications.exists())

    def test_missing_case_returns_404_and_finalized_cases_cannot_be_broadcast(self):
        self.assertEqual(
            self.client.post(reverse("rescue:case-notify-admins", args=(999999,))).status_code,
            404,
        )
        for status in (RescueCase.Status.RESCUED, RescueCase.Status.CLOSED, RescueCase.Status.CANCELLED):
            with self.subTest(status=status):
                RescueCase.objects.filter(pk=self.case.pk).update(status=status)
                self.assertRedirects(self.client.post(self.notify_url()), self.detail_url())
                self.assertFalse(self.case.private_messages.exists())
                self.assertFalse(self.case.notifications.exists())

    def test_assigned_moderator_recipient_can_open_and_reply_privately(self):
        self.client.post(self.notify_url())
        automatic = self.case.private_messages.get(recipient=self.moderator)
        recipient = Client()
        recipient.force_login(self.moderator)
        response = recipient.get(self.message_url())
        self.assertContains(response, self.case.title)
        self.assertContains(response, self.case.address)
        self.assertContains(response, self.detail_url())
        self.assertIn(self.admin, response.context["form"].fields["recipient"].queryset)
        automatic.refresh_from_db()
        self.assertIsNotNone(automatic.read_at)
        reply = "Đã nhận tin, tôi sẽ liên hệ đơn vị cứu hộ."
        self.assertRedirects(recipient.post(self.message_url(), {
            "recipient": self.admin.pk, "body": reply,
        }), self.message_url())
        self.assertTrue(self.case.private_messages.filter(
            sender=self.moderator, recipient=self.admin, body=reply,
        ).exists())
        self.assertTrue(self.case.assignments.filter(assignee=self.moderator, is_active=True).exists())
        self.assertContains(self.client.get(self.message_url()), reply)
        self.assertNotContains(self._get_as(self.other_moderator, self.message_url()), reply)

    def _get_as(self, user, url):
        client = Client()
        client.force_login(user)
        return client.get(url)

    def test_automatic_message_is_hidden_from_reporter_staff_and_unassigned_operator(self):
        self.client.post(self.notify_url())
        automatic = self.case.private_messages.get(recipient=self.moderator)
        for user in (self.reporter, self.operator, self.staff):
            with self.subTest(user=user.email):
                response = self._get_as(user, self.message_url())
                self.assertIn(response.status_code, (403, 404))
                self.assertNotIn(automatic.body, response.content.decode())
                detail = self._get_as(user, self.detail_url())
                self.assertNotContains(detail, automatic.body)
        automatic.refresh_from_db()
        self.assertIsNone(automatic.read_at)

    def test_admin_message_recipient_choices_preserve_active_assignees_and_reject_others(self):
        RescueAssignment.objects.create(
            rescue_case=self.case, assignee=self.operator, assigned_by=self.admin,
        )
        response = self.client.get(self.message_url())
        choices = response.context["form"].fields["recipient"].queryset
        self.assertEqual(set(choices.values_list("pk", flat=True)), {
            self.legacy_admin.pk, self.operator.pk,
        })
        for invalid in (self.reporter, self.staff, self.inactive_admin, self.admin):
            with self.subTest(recipient=invalid.email):
                response = self.client.post(self.message_url(), {
                    "recipient": invalid.pk, "body": "Không được gửi cho người này.",
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn("recipient", response.context["form"].errors)
        self.assertFalse(self.case.private_messages.exists())
        self.assertRedirects(self.client.post(self.message_url(), {
            "recipient": self.operator.pk, "body": "Mang lồng đến địa chỉ trong hồ sơ.",
        }), self.message_url())
        self.assertTrue(self.case.private_messages.filter(recipient=self.operator).exists())

    def test_complete_success_preserves_location_and_adds_case_to_public_map(self):
        before = Client().get(reverse("rescue:case-map"))
        self.assertNotIn(self.case.pk, [item["id"] for item in before.context["map_cases"]])
        address, latitude, longitude = self.case.address, self.case.latitude, self.case.longitude
        self.assertRedirects(self.complete(), self.detail_url())
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.RESCUED)
        self.assertIsNotNone(self.case.closed_at)
        self.assertEqual((self.case.address, self.case.latitude, self.case.longitude),
                         (address, latitude, longitude))
        history = self.case.status_history.get()
        self.assertEqual(history.changed_by, self.admin)
        self.assertEqual(history.from_status, RescueCase.Status.VERIFIED)
        self.assertEqual(history.to_status, RescueCase.Status.RESCUED)
        self.assertEqual(history.note, "Đã kiểm tra kết quả, động vật đã an toàn.")
        guest = Client().get(reverse("rescue:case-map"))
        marker = next(item for item in guest.context["map_cases"] if item["id"] == self.case.pk)
        self.assertTrue(marker["is_approximate"])
        self.assertEqual(marker["latitude"], round(float(latitude), 2))
        self.assertEqual(marker["longitude"], round(float(longitude), 2))
        self.assertNotContains(guest, address)
        self.assertNotContains(guest, self.case.contact_phone)
        admin_map = self.client.get(reverse("rescue:case-map"))
        marker = next(item for item in admin_map.context["map_cases"] if item["id"] == self.case.pk)
        self.assertEqual(marker["address"], address)
        self.assertEqual(marker["latitude"], float(latitude))
        self.assertEqual(marker["longitude"], float(longitude))

    def test_public_location_remains_exact_on_successful_map(self):
        self.case.is_location_private = False
        self.case.save(update_fields=("is_location_private",))
        self.complete()
        response = Client().get(reverse("rescue:case-map"))
        marker = next(item for item in response.context["map_cases"] if item["id"] == self.case.pk)
        self.assertFalse(marker["is_approximate"])
        self.assertEqual(marker["address"], self.case.address)
        self.assertEqual(marker["latitude"], float(self.case.latitude))
        self.assertEqual(marker["longitude"], float(self.case.longitude))

    def test_repeated_success_is_idempotent_and_terminal_case_cannot_reopen(self):
        self.complete()
        self.case.refresh_from_db()
        closed_at = self.case.closed_at
        notification_ids = set(self.case.notifications.values_list("pk", flat=True))
        self.complete(note="Bấm lại nút thành công.")
        self.client.post(reverse("rescue:case-update-status", args=(self.case.pk,)), {
            "status": RescueCase.Status.IN_PROGRESS, "note": "Thử mở lại hồ sơ.",
        })
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.RESCUED)
        self.assertEqual(self.case.closed_at, closed_at)
        self.assertEqual(self.case.status_history.count(), 1)
        self.assertEqual(set(self.case.notifications.values_list("pk", flat=True)), notification_ids)

    def test_success_requires_written_evaluation_and_admin_permission(self):
        for user in (self.reporter, self.operator, self.staff):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertEqual(self.complete().status_code, 403)
        self.client.force_login(self.admin)
        for note in ("", "   "):
            with self.subTest(note=note):
                self.assertRedirects(self.complete(note=note), self.detail_url())
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.assertIsNone(self.case.closed_at)
        self.assertFalse(self.case.status_history.exists())
        self.assertFalse(self.case.notifications.exists())

    def test_success_rejects_missing_or_out_of_bounds_stored_location(self):
        invalid_locations = (
            {"address": ""}, {"address": "   "},
            {"latitude": None}, {"longitude": None},
            {"latitude": Decimal("10.776900"), "longitude": Decimal("106.700900")},
        )
        for changes in invalid_locations:
            with self.subTest(changes=changes):
                case = RescueCase.objects.create(
                    title="Ca chưa có vị trí hợp lệ", description="Cần bổ sung hiện trường.",
                    animal_type=RescueCase.AnimalType.CAT, reporter=self.reporter,
                    status=RescueCase.Status.VERIFIED,
                    address=changes.get("address", self.case.address),
                    latitude=changes.get("latitude", self.case.latitude),
                    longitude=changes.get("longitude", self.case.longitude),
                )
                self.assertRedirects(self.complete(case=case), self.detail_url(case))
                case.refresh_from_db()
                self.assertEqual(case.status, RescueCase.Status.VERIFIED)
                self.assertIsNone(case.closed_at)
                self.assertFalse(case.status_history.exists())
                self.assertFalse(case.notifications.exists())

    def test_completion_is_post_only_and_enforces_csrf(self):
        url = reverse("rescue:case-update-status", args=(self.case.pk,))
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(url, {
            "status": RescueCase.Status.RESCUED, "note": "Đã xử lý.",
        }).status_code, 403)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.assertFalse(CaseStatusHistory.objects.filter(rescue_case=self.case).exists())
        self.assertFalse(Notification.objects.filter(rescue_case=self.case).exists())
        self.assertFalse(RescueCaseMessage.objects.filter(rescue_case=self.case).exists())

    def test_legacy_admin_success_action_cannot_bypass_stored_location_validation(self):
        url = reverse("admin:rescue_rescuecase_quick_status", args=(
            self.case.pk, RescueCase.Status.RESCUED,
        ))
        self.case.longitude = None
        self.case.save(update_fields=("longitude",))
        evaluation = "Đã xem ảnh và kết quả cứu hộ, động vật an toàn."
        response = self.client.post(url, {"note": evaluation}, follow=True)
        self.assertRedirects(response, self.detail_url() + "#case-complete")
        self.assertContains(
            response,
            "Hãy bổ sung địa chỉ và vị trí hợp lệ tại Đà Nẵng trước khi xác nhận thành công.",
        )
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.assertIsNone(self.case.closed_at)
        self.assertFalse(self.case.status_history.exists())
        self.assertFalse(self.case.notifications.exists())

        self.case.longitude = Decimal("108.202167")
        self.case.save(update_fields=("longitude",))
        response = self.client.post(url, {"note": evaluation})
        self.assertRedirects(response, reverse("admin:rescue_rescuecase_changelist"))
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.RESCUED)
        self.assertIsNotNone(self.case.closed_at)
        self.assertEqual(self.case.status_history.get().note, evaluation)
        self.assertEqual(self.case.longitude, Decimal("108.202167"))
        markers = Client().get(reverse("rescue:case-map")).context["map_cases"]
        self.assertIn(self.case.pk, [marker["id"] for marker in markers])
