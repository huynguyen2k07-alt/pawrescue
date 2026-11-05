"""Kiểm tra lỗi gửi form và luồng client → admin → quản trị viên bằng ba phiên riêng."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from support.models import SupportConversation

from .models import Notification, RescueAssignment, RescueCase, RescueCaseImage


@override_settings(SECURE_SSL_REDIRECT=False)
class RequestDeliveryTests(TestCase):
    password = "Delivery-test-only-password-2026"

    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="delivery-admin@example.invalid", password=cls.password,
            full_name="Admin chính kiểm thử",
        )
        cls.moderator = users.objects.create_user(
            email="delivery-moderator@example.invalid", password=cls.password,
            role=users.Role.MODERATOR, full_name="Quản trị viên kiểm thử",
        )
        cls.member = users.objects.create_user(
            email="delivery-client@example.invalid", password=cls.password,
            full_name="Người báo tin kiểm thử",
        )

    def session_for(self, user, host, agent, *, admin_login=False):
        client = Client(
            enforce_csrf_checks=True, HTTP_HOST=host, HTTP_USER_AGENT=agent,
            HTTP_ORIGIN=f"http://{host}",
        )
        route = "admin:login" if admin_login else "accounts:login"
        self.assertEqual(client.get(reverse(route)).status_code, 200)
        result = self.post(client, reverse(route), {
            "username": user.email, "password": self.password,
            "next": reverse("admin:index") if admin_login else reverse("rescue:case-list"),
        })
        self.assertEqual(result.status_code, 302)
        self.assertEqual(int(client.session["_auth_user_id"]), user.pk)
        return client

    def post(self, client, url, data):
        return client.post(url, data, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)

    def setUp(self):
        self.reporter = self.session_for(self.member, "127.0.0.1:8000", "Chrome delivery test")
        self.owner = self.session_for(self.admin, "localhost:8000", "Firefox delivery test", admin_login=True)
        self.reviewer = self.session_for(self.moderator, "localhost:8000", "Firefox moderator test")

    def payload(self, **changes):
        data = {
            "title": "Mèo cần kiểm tra tại cổng chợ",
            "description": "Mèo bị thương ở chân, đang nằm cạnh cổng.",
            "animal_type": "cat", "urgency": "high",
            "address": "Cổng chợ Hàn, 119 Trần Phú, Đà Nẵng",
            "latitude": "16.067525", "longitude": "108.224049",
            "location_confirmed": "on", "is_location_private": "on",
            "contact_phone": "0901234567",
        }
        data.update(changes)
        return data

    def submit_report(self):
        response = self.post(self.reporter, reverse("rescue:case-create"), self.payload())
        case = RescueCase.objects.get(reporter=self.member)
        self.assertRedirects(response, reverse("rescue:case-detail", args=(case.pk,)), fetch_redirect_response=False)
        return case

    def test_missing_location_shows_all_errors_and_preserves_the_report(self):
        data = self.payload(latitude="", longitude="", location_confirmed="")
        response = self.post(self.reporter, reverse("rescue:case-create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="case-form-errors" role="alert"')
        self.assertContains(response, "Chưa gửi được báo cáo tới admin.")
        self.assertContains(response, "Hồ sơ chưa được lưu.")
        self.assertContains(response, 'href="#id_latitude"')
        self.assertContains(response, 'href="#id_longitude"')
        self.assertContains(response, 'href="#id_location_confirmed"')
        self.assertContains(response, data["title"])
        self.assertContains(response, data["address"])
        self.assertContains(response, data["description"])
        self.assertTrue(response.context["form"].fields["latitude"].widget.attrs["autofocus"])
        self.assertContains(response, 'id="manual-coordinates" open')
        self.assertFalse(RescueCase.objects.exists())
        self.assertFalse(RescueCaseImage.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_missing_confirmation_focuses_checkbox_without_discarding_valid_coordinates(self):
        response = self.post(self.reporter, reverse("rescue:case-create"), self.payload(location_confirmed=""))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chưa gửi được báo cáo tới admin.")
        self.assertContains(response, 'href="#id_location_confirmed"')
        form = response.context["form"]
        self.assertEqual(set(form.errors), {"location_confirmed"})
        self.assertTrue(form.fields["location_confirmed"].widget.attrs["autofocus"])
        self.assertEqual(form["latitude"].value(), "16.067525")
        self.assertEqual(form["longitude"].value(), "108.224049")
        self.assertFalse(RescueCase.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_saved_report_reaches_main_admin_across_separate_sessions_and_hostnames(self):
        state_url = reverse("rescue:notification-state")
        before = self.owner.get(state_url)
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json()["unread_count"], 0)
        case = self.submit_report()
        detail_url = reverse("rescue:case-detail", args=(case.pk,))
        confirmation = self.reporter.get(detail_url)
        self.assertContains(confirmation, f"Mã tin báo: #{case.pk}.")
        self.assertEqual(case.status, RescueCase.Status.REPORTED)

        for route in ("admin:index", "admin:rescue_rescuecase_changelist"):
            with self.subTest(route=route):
                page = self.owner.get(reverse(route))
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, case.title)
        updated = self.owner.get(state_url, HTTP_IF_NONE_MATCH=before["ETag"])
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["unread_count"], 1)
        item = updated.json()["items"][0]
        self.assertEqual(item["kind"], Notification.Kind.CASE_REPORTED)
        self.assertEqual(item["url"], detail_url)
        self.assertContains(self.owner.get(item["url"]), case.address)
        self.assertContains(self.reporter.get(reverse("rescue:my-cases")), case.title)
        self.assertEqual(self.reviewer.get(detail_url).status_code, 404)
        self.assertNotContains(self.reviewer.get(reverse("collaborators:dashboard")), case.title)

    def test_three_roles_complete_the_workflow_before_the_case_appears_on_public_map(self):
        case = self.submit_report()
        detail_url = reverse("rescue:case-detail", args=(case.pk,))
        status_url = reverse("rescue:case-update-status", args=(case.pk,))
        public = Client()

        def public_case_ids():
            return [item["id"] for item in public.get(reverse("rescue:case-map")).context["map_cases"]]

        self.assertNotIn(case.pk, public_case_ids())
        self.assertEqual(self.post(self.reporter, status_url, {"status": "rescued", "note": "Thử tự duyệt."}).status_code, 403)
        assigned = self.post(self.owner, reverse("rescue:case-assign", args=(case.pk,)), {
            "assignee": self.moderator.pk, "notes": "Kiểm tra đúng ghim và liên hệ người báo tin.",
        })
        self.assertEqual(assigned.status_code, 302)
        self.assertTrue(RescueAssignment.objects.filter(rescue_case=case, assignee=self.moderator, is_active=True).exists())
        self.assertContains(self.reviewer.get(detail_url), case.address)

        client_message = "Người báo tin cần hướng dẫn thêm về ca đã gửi."
        sent = self.post(self.reporter, reverse("support:chat-send"), {"body": client_message})
        self.assertEqual(sent.status_code, 201)
        conversation = SupportConversation.objects.get(user=self.member)
        admin_reply = "Admin đã nhận tin và đang phối hợp với người phụ trách."
        reply = self.post(self.owner, reverse("support:admin-reply", args=(conversation.pk,)), {"body": admin_reply})
        self.assertEqual(reply.status_code, 302)
        chat = self.reporter.get(reverse("support:chat-state")).json()
        self.assertIn(admin_reply, [message["body"] for message in chat["messages"]])
        self.assertEqual(self.reviewer.get(reverse("support:inbox")).status_code, 403)

        messages_url = reverse("rescue:case-messages", args=(case.pk,))
        instruction = "Chỉ dẫn riêng từ admin: đến đúng ghim và kiểm tra hiện trường."
        self.assertEqual(self.post(self.owner, messages_url, {"recipient": self.moderator.pk, "body": instruction}).status_code, 302)
        self.assertContains(self.reviewer.get(messages_url), instruction)
        acknowledgement = "Quản trị viên đã nhận chỉ dẫn và đang xử lý."
        self.assertEqual(self.post(self.reviewer, messages_url, {"recipient": self.admin.pk, "body": acknowledgement}).status_code, 302)
        self.assertContains(self.owner.get(messages_url), acknowledgement)
        self.assertEqual(self.reporter.get(messages_url).status_code, 404)

        for status in ("verified", "pending_review"):
            changed = self.post(self.reviewer, status_url, {"status": status, "note": "Đã kiểm tra thông tin và kết quả tại hiện trường."})
            self.assertEqual(changed.status_code, 302)
            case.refresh_from_db()
            self.assertEqual(case.status, status)
            self.assertNotIn(case.pk, public_case_ids())
        self.assertEqual(self.post(self.reviewer, status_url, {"status": "rescued", "note": "Thử vượt quyền."}).status_code, 403)
        approved = self.post(self.owner, status_url, {"status": "rescued", "note": "Admin chính đã kiểm tra và duyệt kết quả."})
        self.assertEqual(approved.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.status, RescueCase.Status.RESCUED)
        self.assertIn(case.pk, public_case_ids())
        self.assertFalse(self.member.is_staff)
        self.assertFalse(self.member.is_superuser)
