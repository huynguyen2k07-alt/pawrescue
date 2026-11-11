"""Thông báo cũ không được để lộ ghi chú nội bộ cho người báo hoặc người ngoài."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Notification, RescueAssignment, RescueCase


@override_settings(SECURE_SSL_REDIRECT=False, MAPTILER_API_KEY="")
class LegacyNotificationPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="legacy-private-admin@example.invalid", password="test-password",
        )
        cls.reporter = users.objects.create_user(
            email="legacy-private-reporter@example.invalid", password="test-password",
        )
        cls.helper = users.objects.create_user(
            email="legacy-private-helper@example.invalid", password="test-password",
            role=users.Role.MODERATOR,
        )
        cls.outsider = users.objects.create_user(
            email="legacy-private-outsider@example.invalid", password="test-password",
        )
        cls.case = RescueCase.objects.create(
            title="Ca cứu hộ của người báo", description="Hồ sơ gốc",
            animal_type="cat", reporter=cls.reporter, address="Đà Nẵng",
            status=RescueCase.Status.RESCUED,
        )
        cls.assignment = RescueAssignment.objects.create(
            rescue_case=cls.case, assignee=cls.helper, assigned_by=cls.admin,
        )
        cls.private_title = "Ghi chú riêng LEGACY-TITLE-4528"
        cls.private_message = "Đánh giá nội bộ LEGACY-NOTE-5937, gọi số riêng 0912987654."
        for user in (cls.admin, cls.reporter, cls.helper, cls.outsider):
            for kind in (Notification.Kind.STATUS_CHANGED, Notification.Kind.CASE_UPDATED):
                Notification.objects.create(
                    rescue_case=cls.case, recipient=user, actor=cls.admin,
                    kind=kind, title=cls.private_title, message=cls.private_message,
                )

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_reporter_sees_generic_legacy_events_without_internal_title_or_body(self):
        response = self.client_for(self.reporter).get(reverse("rescue:notification-list"))
        self.assertContains(response, "Trạng thái ca cứu hộ đã thay đổi")
        self.assertContains(response, "Có cập nhật mới từ đội cứu hộ")
        self.assertNotContains(response, self.private_title)
        self.assertNotContains(response, self.private_message)
        self.assertNotContains(response, "0912987654")

    def test_live_toast_title_is_sanitized_without_exposing_legacy_body(self):
        payload = self.client_for(self.reporter).get(reverse("rescue:notification-state")).json()
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual({item["title"] for item in payload["items"]}, {
            "Trạng thái ca cứu hộ đã thay đổi", "Có cập nhật mới từ đội cứu hộ",
        })
        self.assertEqual({item["title"] for item in payload["unread_items"]}, {
            "Trạng thái ca cứu hộ đã thay đổi", "Có cập nhật mới từ đội cứu hộ",
        })
        self.assertNotIn(self.private_title, str(payload))
        self.assertNotIn(self.private_message, str(payload))

    def test_admin_and_active_helper_keep_authorized_legacy_note_access(self):
        for user in (self.admin, self.helper):
            with self.subTest(user=user.email):
                client = self.client_for(user)
                response = client.get(reverse("rescue:notification-list"))
                self.assertContains(response, self.private_title)
                self.assertContains(response, self.private_message)
                payload = client.get(reverse("rescue:notification-state")).json()
                self.assertTrue(all(item["title"] == self.private_title for item in payload["items"]))

    def test_outsider_and_revoked_helper_cannot_read_historical_private_notices(self):
        RescueAssignment.objects.filter(pk=self.assignment.pk).update(is_active=False)
        for user in (self.outsider, self.helper):
            with self.subTest(user=user.email):
                client = self.client_for(user)
                response = client.get(reverse("rescue:notification-list"))
                self.assertNotContains(response, self.private_title)
                self.assertNotContains(response, self.private_message)
                self.assertEqual(client.get(reverse("rescue:notification-state")).json()["items"], [])

    def test_deleted_case_legacy_notice_has_safe_event_content(self):
        Notification.objects.filter(rescue_case=self.case).update(rescue_case=None)
        self.case.delete()
        response = self.client_for(self.reporter).get(reverse("rescue:notification-list"))
        self.assertContains(response, "Trạng thái ca cứu hộ đã thay đổi")
        self.assertNotContains(response, self.private_title)
        self.assertNotContains(response, self.private_message)

    def test_display_projection_does_not_change_original_notification_rows(self):
        before = list(Notification.objects.order_by("pk").values_list("pk", "title", "message"))
        self.client_for(self.reporter).get(reverse("rescue:notification-list"))
        self.client_for(self.reporter).get(reverse("rescue:notification-state"))
        self.assertEqual(list(Notification.objects.order_by("pk").values_list("pk", "title", "message")), before)
