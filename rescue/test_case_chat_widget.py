"""Hộp chat dùng chung vẫn giữ quyền và lịch sử trao đổi riêng từng ca."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Notification, RescueAssignment, RescueCase, RescueCaseMessage


@override_settings(SECURE_SSL_REDIRECT=False)
class CaseChatWidgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="case-widget-admin@example.com", password="test-password", full_name="",
        )
        cls.other_admin = users.objects.create_superuser(
            email="case-widget-other-admin@example.com", password="test-password", full_name="Admin thứ hai",
        )
        cls.partner = users.objects.create_user(
            email="case-widget-partner@example.com", password="test-password", full_name="",
            role=users.Role.MODERATOR,
        )
        cls.other_partner = users.objects.create_user(
            email="case-widget-other-partner@example.com", password="test-password", full_name="Trung tâm khác",
            role=users.Role.MODERATOR,
        )
        cls.reporter = users.objects.create_user(
            email="case-widget-reporter@example.com", password="test-password", full_name="Người báo",
        )
        cls.staff = users.objects.create_user(
            email="case-widget-staff@example.com", password="test-password", full_name="Nhân viên",
            is_staff=True,
        )
        cls.case = RescueCase.objects.create(
            title="Ca thử hộp chat", description="Cần hỗ trợ cứu hộ.",
            animal_type=RescueCase.AnimalType.CAT, reporter=cls.reporter,
            address="Địa chỉ riêng chỉ đội cứu hộ biết", contact_name="Tên liên hệ riêng",
            contact_phone="0901234567", is_location_private=True,
        )
        cls.assignment = RescueAssignment.objects.create(
            rescue_case=cls.case, assignee=cls.partner, assigned_by=cls.admin,
        )
        RescueAssignment.objects.create(
            rescue_case=cls.case, assignee=cls.other_partner, assigned_by=cls.admin,
        )

    def setUp(self):
        self.url = reverse("rescue:case-messages", args=(self.case.pk,))
        self.client.force_login(self.admin)

    def get_state(self):
        return self.client.get(self.url, HTTP_ACCEPT="application/json")

    def send(self, recipient, body="Chỉ dẫn riêng cho người nhận"):
        return self.client.post(self.url, {
            "recipient": recipient.pk, "body": body,
        }, HTTP_ACCEPT="application/json")

    def test_state_has_safe_names_and_no_reporter_contact_metadata(self):
        RescueCaseMessage.objects.create(
            rescue_case=self.case, sender=self.admin, recipient=self.partner, body="Tin điều phối",
        )
        response = self.get_state()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["case_id"], self.case.pk)
        self.assertEqual(data["title"], self.case.title)
        self.assertEqual(data["messages"][0]["sender_name"], "Admin")
        self.assertEqual(data["messages"][0]["recipient_name"], "Cộng tác viên")
        self.assertTrue(data["messages"][0]["is_own"])
        self.assertEqual(data["unread_count"], 0)
        for value in (
            self.admin.email, self.partner.email, self.reporter.email,
            self.case.address, self.case.contact_name, self.case.contact_phone,
        ):
            self.assertNotContains(response, value)
        for directive in ("private", "no-store", "no-cache"):
            self.assertIn(directive, response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])

    def test_each_partner_only_sees_own_messages_and_read_receipts(self):
        inbound = RescueCaseMessage.objects.create(
            rescue_case=self.case, sender=self.admin, recipient=self.partner, body="Tin đến",
        )
        outbound = RescueCaseMessage.objects.create(
            rescue_case=self.case, sender=self.partner, recipient=self.admin, body="Tin gửi",
        )
        other = RescueCaseMessage.objects.create(
            rescue_case=self.case, sender=self.other_admin, recipient=self.other_partner,
            body="Trao đổi của hai người khác",
        )
        self.client.force_login(self.partner)
        data = self.get_state().json()
        self.assertEqual([item["id"] for item in data["messages"]], [inbound.pk, outbound.pk])
        self.assertFalse(data["messages"][0]["is_own"])
        self.assertTrue(data["messages"][1]["is_own"])
        self.assertEqual(data["unread_count"], 0)
        inbound.refresh_from_db()
        outbound.refresh_from_db()
        other.refresh_from_db()
        self.assertIsNotNone(inbound.read_at)
        self.assertIsNone(outbound.read_at)
        self.assertIsNone(other.read_at)

    def test_json_get_does_not_mark_other_cases_or_global_notifications_read(self):
        other_case = RescueCase.objects.create(
            title="Ca khác", description="Không mở trong hộp chat này",
            animal_type=RescueCase.AnimalType.CAT, address="Địa chỉ khác",
        )
        other_message = RescueCaseMessage.objects.create(
            rescue_case=other_case, sender=self.partner, recipient=self.admin, body="Tin ca khác",
        )
        notification = Notification.objects.create(
            recipient=self.admin, rescue_case=self.case, kind=Notification.Kind.CASE_MESSAGE,
            title="Thông báo chưa đọc", message="Giữ nguyên trạng thái chuông thông báo",
        )
        self.get_state()
        other_message.refresh_from_db()
        notification.refresh_from_db()
        self.assertIsNone(other_message.read_at)
        self.assertFalse(notification.is_read)

    def test_admin_send_creates_existing_private_message_and_targeted_notification(self):
        response = self.send(self.partner, "Đến cổng bên hông")
        self.assertEqual(response.status_code, 201)
        stored = RescueCaseMessage.objects.get()
        self.assertEqual(stored.sender, self.admin)
        self.assertEqual(stored.recipient, self.partner)
        self.assertEqual(stored.body, "Đến cổng bên hông")
        self.assertEqual(response.json()["messages"][0]["id"], stored.pk)
        notice = Notification.objects.get(kind=Notification.Kind.CASE_MESSAGE)
        self.assertEqual(notice.recipient, self.partner)
        self.assertEqual(notice.target_url, self.url)

    def test_partner_reply_and_post_snapshot_do_not_mark_inbound_read(self):
        inbound = RescueCaseMessage.objects.create(
            rescue_case=self.case, sender=self.admin, recipient=self.partner, body="Chưa mở",
        )
        self.client.force_login(self.partner)
        response = self.send(self.admin, "Đã tới hiện trường")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["unread_count"], 1)
        inbound.refresh_from_db()
        self.assertIsNone(inbound.read_at)
        self.assertEqual(set(item["id"] for item in response.json()["recipients"]), {
            self.admin.pk, self.other_admin.pk,
        })

    def test_admin_recipient_list_excludes_reporter_inactive_and_unassigned_users(self):
        self.other_partner.is_active = False
        self.other_partner.save(update_fields=("is_active",))
        unassigned = get_user_model().objects.create_user(
            email="case-widget-unassigned@example.com", password="test-password",
            full_name="Chưa được giao ca", role=get_user_model().Role.MODERATOR,
        )
        recipient_ids = {item["id"] for item in self.get_state().json()["recipients"]}
        self.assertEqual(recipient_ids, {self.partner.pk, self.other_admin.pk})
        self.assertNotIn(unassigned.pk, recipient_ids)

    def test_invalid_recipient_empty_or_overlong_body_returns_json_without_saving(self):
        for recipient, body in (
            (self.reporter, "Không được gửi cho người báo"),
            (self.partner, " "),
            (self.partner, "a" * 2001),
        ):
            with self.subTest(recipient=recipient.pk, body_length=len(body)):
                response = self.send(recipient, body)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json()["error"])
                self.assertTrue(response.json()["errors"])
        self.assertFalse(RescueCaseMessage.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_reporter_staff_and_unassigned_partner_cannot_read_or_send(self):
        unassigned = get_user_model().objects.create_user(
            email="case-widget-denied@example.com", password="test-password",
            full_name="Người ngoài ca", role=get_user_model().Role.MODERATOR,
        )
        for user in (self.reporter, self.staff, unassigned):
            with self.subTest(user=user.pk):
                self.client.force_login(user)
                self.assertEqual(self.get_state().status_code, 404)
                self.assertEqual(self.send(self.admin).status_code, 404)
        self.assertFalse(RescueCaseMessage.objects.exists())

    def test_ended_assignment_blocks_read_send_and_receipts(self):
        message = RescueCaseMessage.objects.create(
            rescue_case=self.case, sender=self.admin, recipient=self.partner, body="Nội dung đã giao",
        )
        self.assignment.is_active = False
        self.assignment.save(update_fields=("is_active",))
        self.client.force_login(self.partner)
        self.assertEqual(self.get_state().status_code, 404)
        self.assertEqual(self.send(self.admin).status_code, 404)
        message.refresh_from_db()
        self.assertIsNone(message.read_at)
        self.assertEqual(RescueCaseMessage.objects.count(), 1)
        self.client.force_login(self.admin)
        self.assertEqual(self.send(self.partner).status_code, 400)

    def test_html_page_and_redirect_still_use_existing_history(self):
        response = self.client.post(self.url, {"recipient": self.partner.pk, "body": "Tin từ trang cũ"})
        self.assertRedirects(response, self.url)
        self.assertContains(self.client.get(self.url), "Tin từ trang cũ")
        self.assertEqual(RescueCaseMessage.objects.count(), 1)

    def test_json_post_still_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(self.url, {"recipient": self.partner.pk, "body": "Thiếu CSRF"},
                               HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(RescueCaseMessage.objects.exists())

    def test_anonymous_access_keeps_login_requirement(self):
        self.client.logout()
        response = self.get_state()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("accounts:login")))
