"""Kiểm tra đồng bộ thông báo không tải lại trang và không lộ thông tin riêng."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from support.models import SupportConversation, SupportMessage

from .models import Notification, RescueAssignment, RescueCase
from .notification_live import notification_state


@override_settings(SECURE_SSL_REDIRECT=False)
class NotificationLiveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.member = users.objects.create_user(email="live-member@example.com", password="test-password")
        cls.other = users.objects.create_user(email="live-other@example.com", password="test-password")
        cls.admin = users.objects.create_superuser(email="live-admin@example.com", password="test-password")
        cls.operator = users.objects.create_user(
            email="live-operator@example.com", password="test-password", role=users.Role.COLLABORATOR,
        )
        cls.moderator = users.objects.create_user(
            email="live-moderator@example.com", password="test-password", role=users.Role.MODERATOR,
        )
        cls.case = RescueCase.objects.create(
            title="Hồ sơ chưa công khai", description="Nội dung riêng cần bảo vệ.",
            animal_type=RescueCase.AnimalType.CAT, reporter=cls.other,
            address="Địa chỉ riêng không được gửi trong thông báo trực tiếp",
            contact_phone="0901234567", latitude="16.054407", longitude="108.202167",
            is_location_private=True,
        )

    def setUp(self):
        self.url = reverse("rescue:notification-state")
        self.client.force_login(self.member)

    def test_mark_read_returns_private_json_without_opening_the_notification_target(self):
        item = self.notification(target_url="https://outside.example/leave/")
        other = self.notification(recipient=self.other)
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.member)
        secured.get(reverse("rescue:notification-list"))
        response = secured.post(
            reverse("rescue:notification-open", args=(item.pk,)),
            HTTP_ACCEPT="application/json",
            HTTP_X_CSRFTOKEN=secured.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Location", response)
        self.assert_private_response(response)
        data = response.json()
        self.assertEqual(data["user_id"], self.member.pk)
        self.assertEqual(data["unread_count"], 0)
        self.assertTrue(data["items"][0]["is_read"])
        self.assertNotIn(item.message, response.content.decode())
        self.assertEqual(data, secured.get(self.url).json())
        item.refresh_from_db()
        other.refresh_from_db()
        self.assertIsNotNone(item.read_at)
        self.assertFalse(other.is_read)

    def test_mark_all_json_only_updates_available_notifications_of_the_current_user(self):
        own = self.notification()
        other = self.notification(recipient=self.other)
        unavailable = self.notification(rescue_case=self.case)
        response = self.client.post(reverse("rescue:notification-read-all"), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assert_private_response(response)
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertEqual(response.json()["total_count"], 1)
        for item, expected in ((own, True), (other, False), (unavailable, False)):
            item.refresh_from_db()
            self.assertEqual(item.is_read, expected)

    def test_read_actions_reject_get_missing_csrf_and_other_users_ids(self):
        own = self.notification()
        other = self.notification(recipient=self.other)
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.member)
        for url in (reverse("rescue:notification-open", args=(own.pk,)), reverse("rescue:notification-read-all")):
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(secured.post(url, HTTP_ACCEPT="application/json").status_code, 403)
        response = self.client.post(reverse("rescue:notification-open", args=(other.pk,)), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 404)
        own.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(own.is_read)
        self.assertFalse(other.is_read)

    def test_without_javascript_reading_retains_the_selected_list_page_and_filter(self):
        item = self.notification(target_url="/support/")
        for url in (reverse("rescue:notification-open", args=(item.pk,)), reverse("rescue:notification-read-all")):
            response = self.client.post(url, {"filter": "unread", "page": "2", "next": "https://outside.example/"})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response["Location"], reverse("rescue:notification-list") + "?filter=unread&page=2")

    def notification(self, **overrides):
        values = {
            "recipient": self.member, "actor": self.other,
            "kind": Notification.Kind.SUPPORT_MESSAGE,
            "title": "Bạn có một thông báo mới", "message": "Nội dung riêng bí mật",
        }
        values.update(overrides)
        return Notification.objects.create(**values)

    def state(self, user=None, **headers):
        if user is not None:
            self.client.force_login(user)
        return self.client.get(self.url, **headers)

    def assert_private_response(self, response):
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("cookie", response["Vary"].lower())

    def test_anonymous_and_inactive_users_get_json_401(self):
        self.client.logout()
        response = self.state()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(set(response.json()), {"error"})
        self.assert_private_response(response)
        inactive = get_user_model().objects.create_user(
            email="live-inactive@example.com", password="test-password", is_active=False,
        )
        request = RequestFactory().get(self.url)
        request.user = inactive
        response = notification_state(request)
        self.assertEqual(response.status_code, 401)
        self.assert_private_response(response)

    def test_only_get_is_supported_and_get_needs_no_csrf_token(self):
        secured_client = Client(enforce_csrf_checks=True)
        secured_client.force_login(self.member)
        self.assertEqual(secured_client.get(self.url).status_code, 200)
        for method in ("post", "put", "delete", "head", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "GET")
                self.assert_private_response(response)

    def test_empty_schema_and_payload_omit_private_fields(self):
        empty = self.state().json()
        self.assertEqual(set(empty), {
            "user_id", "version", "unread_count", "total_count", "latest_id",
            "support_unread_count", "items", "unread_items",
        })
        self.assertEqual((empty["user_id"], empty["unread_count"], empty["total_count"], empty["latest_id"]),
                         (self.member.pk, 0, 0, 0))
        self.assertRegex(empty["version"], r"^[0-9a-f]{64}$")
        item = self.notification(rescue_case=self.case)
        self.case.reporter = self.member
        self.case.save(update_fields=("reporter",))
        response = self.state()
        data = response.json()
        self.assertEqual(set(data["items"][0]), {
            "id", "kind", "title", "is_read", "created_at", "url", "open_url",
        })
        self.assertEqual(data["items"][0]["open_url"], reverse("rescue:notification-open", args=(item.pk,)))
        for secret in (item.message, self.case.description, self.case.address, self.case.contact_phone,
                       str(self.case.latitude), str(self.case.longitude), self.other.email):
            self.assertNotContains(response, secret)
        self.assert_private_response(response)

    def test_recipient_scope_ignores_arbitrary_user_and_filter_parameters(self):
        own = self.notification()
        self.notification(recipient=self.other, title="Không dành cho người hiện tại")
        response = self.client.get(self.url, {"user_id": self.other.pk, "filter": "all", "limit": 10000})
        data = response.json()
        self.assertEqual(data["user_id"], self.member.pk)
        self.assertEqual([item["id"] for item in data["items"]], [own.pk])
        self.assertEqual(data["total_count"], 1)

    def test_archived_adoption_and_nonadmin_case_report_notifications_are_hidden(self):
        own = self.notification()
        for kind in (Notification.Kind.ADOPTION_SUBMITTED, Notification.Kind.ADOPTION_REVIEWED,
                     Notification.Kind.ADOPTION_FOLLOW_UP, Notification.Kind.ADOPTION_SAFETY,
                     Notification.Kind.CASE_REPORTED):
            self.notification(kind=kind)
        data = self.state().json()
        self.assertEqual([item["id"] for item in data["items"]], [own.pk])
        self.assertEqual(data["total_count"], 1)
        admin_item = self.notification(recipient=self.admin, kind=Notification.Kind.CASE_REPORTED,
                                       rescue_case=self.case)
        admin_data = self.state(self.admin).json()
        self.assertEqual([item["id"] for item in admin_data["items"]], [admin_item.pk])

    def test_private_case_visibility_and_assignment_revocation_update_version(self):
        private = self.notification(recipient=self.moderator, rescue_case=self.case,
                                    kind=Notification.Kind.CASE_ASSIGNED)
        initial = self.state(self.moderator).json()
        self.assertEqual(initial["items"], [])
        assignment = RescueAssignment.objects.create(
            rescue_case=self.case, assignee=self.moderator, assigned_by=self.admin,
        )
        assigned = self.state().json()
        self.assertEqual([item["id"] for item in assigned["items"]], [private.pk])
        self.assertNotEqual(initial["version"], assigned["version"])
        assignment.is_active = False
        assignment.save(update_fields=("is_active",))
        revoked = self.state().json()
        self.assertEqual(revoked["items"], [])
        self.assertNotEqual(assigned["version"], revoked["version"])

    def test_get_does_not_mark_notifications_or_support_messages_read(self):
        notification = self.notification(recipient=self.admin)
        conversation = SupportConversation.objects.create(user=self.member)
        message = SupportMessage.objects.create(
            conversation=conversation, sender=self.member,
            sender_role=SupportMessage.SenderRole.USER, body="Không tự đánh dấu đã đọc.",
        )
        response = self.state(self.admin)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["support_unread_count"], 1)
        notification.refresh_from_db()
        message.refresh_from_db()
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)
        self.assertFalse(message.is_read_by_admin)

    def test_new_read_and_deleted_notifications_change_snapshot_and_etag(self):
        initial = self.state().json()
        item = self.notification()
        added = self.state().json()
        self.assertEqual((added["unread_count"], added["latest_id"]), (1, item.pk))
        self.assertNotEqual(initial["version"], added["version"])
        item.mark_as_read()
        read = self.state().json()
        self.assertEqual(read["unread_count"], 0)
        self.assertEqual(read["unread_items"], [])
        self.assertTrue(read["items"][0]["is_read"])
        self.assertNotEqual(added["version"], read["version"])
        item.delete()
        deleted = self.state().json()
        self.assertEqual(deleted, initial)

    def test_old_read_changes_and_deletions_update_counts_outside_recent_window(self):
        items = [self.notification() for _ in range(25)]
        initial = self.state().json()
        items[0].mark_as_read()
        changed = self.state().json()
        self.assertEqual(initial["items"], changed["items"])
        self.assertEqual(initial["unread_count"] - 1, changed["unread_count"])
        self.assertNotEqual(initial["version"], changed["version"])
        items[1].delete()
        deleted = self.state().json()
        self.assertEqual(deleted["total_count"], 24)
        self.assertNotEqual(changed["version"], deleted["version"])

    def test_twenty_recent_and_twenty_unread_items_have_stable_tie_order(self):
        unread = [self.notification() for _ in range(25)]
        read = [self.notification(is_read=True) for _ in range(25)]
        fixed_time = timezone.now() - timedelta(minutes=1)
        Notification.objects.all().update(created_at=fixed_time)
        data = self.state().json()
        self.assertEqual(data["total_count"], 50)
        self.assertEqual(data["unread_count"], 25)
        self.assertEqual(data["latest_id"], read[-1].pk)
        self.assertEqual([item["id"] for item in data["items"]], [item.pk for item in read[-20:][::-1]])
        self.assertEqual([item["id"] for item in data["unread_items"]], [item.pk for item in unread[-20:][::-1]])

    def test_etag_304_is_private_and_other_users_never_share_a_snapshot(self):
        self.notification()
        first = self.state()
        self.assertEqual(first["ETag"], f'"{first.json()["version"]}"')
        unchanged = self.state(HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(unchanged.status_code, 304)
        self.assertEqual(unchanged.content, b"")
        self.assert_private_response(unchanged)
        other = self.state(self.other, HTTP_IF_NONE_MATCH=first["ETag"])
        self.assertEqual(other.status_code, 200)
        self.assertNotEqual(other["ETag"], first["ETag"])
        self.assertEqual(self.state(HTTP_IF_NONE_MATCH='W/' + other["ETag"]).status_code, 200)

    def test_safe_local_and_same_origin_targets_return_local_urls(self):
        for target, expected in (
            ("/notifications/?filter=unread#list", "/notifications/?filter=unread#list"),
            ("http://testserver/notifications/?filter=unread", "/notifications/?filter=unread"),
        ):
            with self.subTest(target=target):
                item = self.notification(target_url=target)
                self.assertEqual(self.state().json()["items"][0]["url"], expected)
                item.delete()

    def test_external_scheme_relative_and_malformed_targets_use_safe_fallbacks(self):
        unsafe_targets = (
            "https://evil.example/steal", "//evil.example/steal", "///evil.example/steal",
            "//testserver/notifications/", "http://testserver.evil.example/steal",
            "https://testserver/notifications/", "javascript:alert(1)",
            "data:text/html,hello", "/\\evil.example/steal", "http://[broken",
            "http://testserver//evil.example/steal", "/notifications/\n//evil.example",
        )
        for target in unsafe_targets:
            with self.subTest(target=target):
                item = self.notification(target_url=target)
                self.assertEqual(self.state().json()["items"][0]["url"], reverse("rescue:notification-list"))
                item.delete()
        item = self.notification(recipient=self.admin, rescue_case=self.case,
                                 target_url="https://evil.example/steal")
        self.assertEqual(self.state(self.admin).json()["items"][0]["url"],
                         reverse("rescue:case-detail", args=(self.case.pk,)))

    def test_https_target_must_match_https_request_origin(self):
        item = self.notification(target_url="https://testserver/notifications/")
        response = self.client.get(self.url, secure=True)
        self.assertEqual(response.json()["items"][0]["url"], "/notifications/")
        item.target_url = "http://testserver/notifications/"
        item.save(update_fields=("target_url",))
        response = self.client.get(self.url, secure=True)
        self.assertEqual(response.json()["items"][0]["url"], reverse("rescue:notification-list"))

    def test_support_count_uses_operator_scope_and_changes_version_after_read(self):
        conversations = [
            SupportConversation.objects.create(user=self.member),
            SupportConversation.objects.create(user=self.other, assigned_to=self.operator),
            SupportConversation.objects.create(user=self.moderator, assigned_to=self.admin),
        ]
        messages = [
            SupportMessage.objects.create(
                conversation=conversation, sender=conversation.user,
                sender_role=SupportMessage.SenderRole.USER, body="Tin nhắn cần trả lời.",
            ) for conversation in conversations
        ]
        SupportMessage.objects.create(
            conversation=conversations[0], sender=self.admin,
            sender_role=SupportMessage.SenderRole.ADMIN, body="Phản hồi chưa đọc của người dùng.",
        )
        for user, expected in ((self.admin, 3), (self.operator, 1), (self.moderator, 0), (self.member, 0)):
            with self.subTest(role=user.role, admin=user.is_superuser):
                self.assertEqual(self.state(user).json()["support_unread_count"], expected)
        initial = self.state(self.admin).json()
        messages[0].is_read_by_admin = True
        messages[0].save(update_fields=("is_read_by_admin",))
        read = self.state().json()
        self.assertEqual(read["support_unread_count"], 2)
        self.assertNotEqual(initial["version"], read["version"])

    def test_nonoperators_do_not_query_user_widget_counter(self):
        with patch("rescue.notification_live.support_chat") as support_context:
            self.assertEqual(self.state().json()["support_unread_count"], 0)
        support_context.assert_not_called()
