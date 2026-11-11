"""Kiểm tra thông báo tự cập nhật có mặt trên mọi khu vực và giữ đúng quyền xem."""

from collections import Counter
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.template import engines
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from support.models import SupportConversation, SupportMessage

from .models import CommunityFeedback, Notification, RescueCase
from .notifications import available_notifications


class _NotificationMarkup(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.elements = []
        self.badge_texts = []
        self._badge_parts = None
        self._badge_depth = 0
        self.feed(response.content.decode())

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.elements.append((tag, attrs))
        if tag == "span":
            if "data-notification-count" in attrs:
                self._badge_parts = []
                self._badge_depth = 1
            elif self._badge_parts is not None:
                self._badge_depth += 1

    def handle_endtag(self, tag):
        if tag == "span" and self._badge_parts is not None:
            self._badge_depth -= 1
            if self._badge_depth == 0:
                self.badge_texts.append("".join(self._badge_parts).strip())
                self._badge_parts = None

    def handle_data(self, data):
        if self._badge_parts is not None:
            self._badge_parts.append(data)

    def with_attribute(self, name):
        return [(tag, attrs) for tag, attrs in self.elements if name in attrs]


@override_settings(SECURE_SSL_REDIRECT=False)
class LiveNotificationTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="live-template-admin@example.com", password="test-password",
            full_name="Quản trị thông báo",
        )
        cls.member = users.objects.create_user(
            email="live-template-member@example.com", password="test-password",
            full_name="Người báo tin",
        )
        cls.other_member = users.objects.create_user(
            email="live-template-other@example.com", password="test-password",
        )
        cls.own_case = RescueCase.objects.create(
            title="Tin riêng của người báo", description="Cần xác minh tại hiện trường.",
            reporter=cls.member, animal_type=RescueCase.AnimalType.CAT,
            address="Hải Châu, Đà Nẵng", latitude="16.054407", longitude="108.202167",
            is_location_private=True,
        )
        cls.hidden_case = RescueCase.objects.create(
            title="Hồ sơ riêng của người khác", description="Nội dung không được tiết lộ.",
            reporter=cls.other_member, animal_type=RescueCase.AnimalType.DOG,
            address="Địa chỉ riêng không được tiết lộ", is_location_private=True,
        )
        cls.member_unread = Notification.objects.create(
            recipient=cls.member, kind=Notification.Kind.STATUS_CHANGED,
            title="Đã tiếp nhận tin của bạn", rescue_case=cls.own_case,
        )
        cls.member_read = Notification.objects.create(
            recipient=cls.member, kind=Notification.Kind.SUPPORT_MESSAGE,
            title="Tin hỗ trợ đã đọc", is_read=True,
        )
        cls.admin_unread = Notification.objects.create(
            recipient=cls.admin, kind=Notification.Kind.CASE_REPORTED,
            title="Có tin cứu hộ cần duyệt", rescue_case=cls.hidden_case,
        )
        Notification.objects.create(
            recipient=cls.admin, kind=Notification.Kind.FEEDBACK_RECEIVED,
            title="Có góp ý cộng đồng",
        )
        cls.admin_read = Notification.objects.create(
            recipient=cls.admin, kind=Notification.Kind.DONATION_SUBMITTED,
            title="Hồ sơ đóng góp đã đọc", is_read=True,
        )
        for user in (cls.admin, cls.member):
            Notification.objects.create(
                recipient=user, kind=Notification.Kind.ADOPTION_SUBMITTED,
                title="Thông báo nhận nuôi đã lưu trữ",
            )
        Notification.objects.create(
            recipient=cls.member, kind=Notification.Kind.CASE_REPORTED,
            rescue_case=cls.own_case, title="Thông báo tin mới chỉ dành cho quản trị chính",
        )
        Notification.objects.create(
            recipient=cls.member, kind=Notification.Kind.STATUS_CHANGED,
            rescue_case=cls.hidden_case, title="Thông tin hồ sơ không thuộc quyền xem",
        )
        cls.conversation = SupportConversation.objects.create(user=cls.member)
        SupportMessage.objects.create(
            conversation=cls.conversation, sender=cls.member,
            sender_role=SupportMessage.SenderRole.USER, body="Cần hỗ trợ tin cứu hộ.",
        )

    def assert_live_navigation(self, response, user):
        self.assertEqual(response.status_code, 200)
        markup = _NotificationMarkup(response)
        roots = markup.with_attribute("data-live-notifications")
        self.assertEqual(len(roots), 1)
        root = roots[0][1]
        self.assertEqual(root["data-state-url"], reverse("rescue:notification-state"))
        self.assertEqual(root["data-list-url"], reverse("rescue:notification-list"))
        self.assertEqual(root["data-user-id"], str(user.pk))
        visible = available_notifications(user)
        expected_latest = visible.order_by("-pk").values_list("pk", flat=True).first() or 0
        self.assertEqual(root["data-latest-id"], str(expected_latest))

        bells = markup.with_attribute("data-notification-link")
        self.assertEqual(len(bells), 1)
        tag, bell = bells[0]
        self.assertEqual(tag, "a")
        self.assertEqual(bell["href"], reverse("rescue:notification-list"))
        self.assertNotIn("onclick", bell)
        badges = markup.with_attribute("data-notification-count")
        self.assertEqual(len(badges), 1)
        expected_unread = visible.filter(is_read=False).count()
        self.assertEqual("hidden" in badges[0][1], expected_unread == 0)
        self.assertEqual(markup.badge_texts, [str(expected_unread)])
        self.assertContains(response, "notifications-live.js")
        scripts = [attrs["src"] for tag, attrs in markup.elements if tag == "script" and attrs.get("src")]
        self.assertEqual(sum("/js/notifications-live.js" in src for src in scripts), 1)
        ids = [attrs["id"] for _, attrs in markup.elements if attrs.get("id")]
        self.assertFalse([value for value, count in Counter(ids).items() if count > 1])
        self.assertEqual(response.context["unread_notification_count"], expected_unread)
        return markup

    def test_live_bell_is_available_across_public_features(self):
        self.client.force_login(self.admin)
        for name in (
            "rescue:case-list", "rescue:case-map", "rescue:case-create",
            "rescue:my-cases", "rescue:knowledge-list", "rescue:team",
            "rescue:notification-list", "support:inbox", "donations:campaign-list",
            "donations:my-donations", "accounts:profile",
        ):
            with self.subTest(route=name):
                self.assert_live_navigation(self.client.get(reverse(name)), self.admin)

    def test_django_admin_index_and_change_form_share_the_same_live_bell(self):
        self.client.force_login(self.admin)
        paths = (
            reverse("admin:index"),
            reverse("admin:rescue_rescuecase_change", args=(self.own_case.pk,)) + "?edit=1",
            reverse("admin:accounts_user_change", args=(self.member.pk,)),
        )
        for path in paths:
            with self.subTest(path=path):
                markup = self.assert_live_navigation(self.client.get(path), self.admin)
                self.assertTrue(markup.with_attribute("data-support-unread-count"))

    def test_member_baseline_excludes_archived_and_inaccessible_notifications(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("rescue:notification-list"))
        self.assert_live_navigation(response, self.member)
        self.assertEqual(response.context["unread_notification_count"], 1)
        self.assertContains(response, "Trạng thái ca cứu hộ đã thay đổi")
        self.assertIn(self.member_unread.pk, [item.pk for item in response.context["page_obj"]])
        self.assertContains(response, self.member_read.title)
        for text in (
            "Thông báo nhận nuôi đã lưu trữ", "Thông tin hồ sơ không thuộc quyền xem",
            "Thông báo tin mới chỉ dành cho quản trị chính", self.admin_unread.title,
            self.hidden_case.address,
        ):
            self.assertNotContains(response, text)

    def test_notification_page_works_with_the_running_servers_original_tag_registry(self):
        self.client.force_login(self.admin)
        engine = engines["django"].engine
        original_libraries = dict(engine.template_libraries)
        original_libraries.pop("notification_tags", None)
        for loader in engine.template_loaders:
            if hasattr(loader, "reset"):
                loader.reset()
        with patch.object(engine, "template_libraries", original_libraries):
            response = self.client.get(reverse("rescue:notification-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.admin_unread.title)
        self.assertContains(response, "Thông báo của bạn")

    def test_notification_links_match_live_notices_and_open_the_content(self):
        self.member_unread.target_url = reverse("rescue:case-detail", args=(self.own_case.pk,))
        self.member_unread.save(update_fields=("target_url",))
        self.client.force_login(self.member)
        response = self.client.get(reverse("rescue:notification-list"))
        page_item = next(item for item in response.context["page_obj"] if item.pk == self.member_unread.pk)
        snapshot = self.client.get(reverse("rescue:notification-state")).json()
        live_item = next(item for item in snapshot["items"] if item["id"] == page_item.pk)
        self.assertEqual(page_item.destination_url, live_item["url"])
        destination = self.client.get(page_item.destination_url)
        self.assertEqual(destination.status_code, 200)
        self.assertContains(destination, self.own_case.title)
        self.member_unread.refresh_from_db()
        self.assertFalse(self.member_unread.is_read)

        marked = self.client.post(live_item["open_url"], follow=True)
        self.assertEqual(marked.status_code, 200)
        self.assertRedirects(marked, reverse("rescue:notification-list"))
        self.assertContains(marked, "Thông báo của bạn")
        self.member_unread.refresh_from_db()
        self.assertTrue(self.member_unread.is_read)

    def test_zero_unread_keeps_a_hidden_badge_ready_for_future_updates(self):
        available_notifications(self.member).update(is_read=True)
        self.client.force_login(self.member)
        self.assert_live_navigation(self.client.get(reverse("rescue:knowledge-list")), self.member)

    def test_zero_available_notifications_has_zero_latest_id(self):
        self.client.force_login(self.other_member)
        markup = self.assert_live_navigation(self.client.get(reverse("rescue:team")), self.other_member)
        self.assertEqual(markup.with_attribute("data-live-notifications")[0][1]["data-latest-id"], "0")

    def test_guest_pages_do_not_start_authenticated_notification_requests(self):
        for name in ("rescue:case-list", "rescue:knowledge-list", "donations:campaign-list"):
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                markup = _NotificationMarkup(response)
                self.assertFalse(markup.with_attribute("data-live-notifications"))
                self.assertFalse(markup.with_attribute("data-notification-link"))

    def test_notification_list_declares_filter_page_and_csrf_for_live_rows(self):
        self.client.force_login(self.member)
        for selected_filter in ("all", "unread"):
            with self.subTest(selected_filter=selected_filter):
                response = self.client.get(reverse("rescue:notification-list"), {"filter": selected_filter})
                markup = self.assert_live_navigation(response, self.member)
                lists = markup.with_attribute("data-live-notification-list")
                self.assertEqual(len(lists), 1)
                attrs = lists[0][1]
                self.assertEqual(attrs["data-filter"], selected_filter)
                self.assertEqual(attrs["data-page"], "1")
                self.assertTrue(attrs.get("data-csrf-token"))
                self.assertContains(response, reverse("rescue:notification-open", args=(self.member_unread.pk,)))
                if selected_filter == "unread":
                    self.assertNotContains(response, self.member_read.title)

    def test_page_two_retains_its_own_rows_and_declares_its_page_number(self):
        Notification.objects.bulk_create([
            Notification(
                recipient=self.member, kind=Notification.Kind.SUPPORT_MESSAGE,
                title=f"Thông báo bổ sung {number:02d}",
            )
            for number in range(21)
        ])
        self.client.force_login(self.member)
        response = self.client.get(reverse("rescue:notification-list"), {"page": 2})
        markup = self.assert_live_navigation(response, self.member)
        attrs = markup.with_attribute("data-live-notification-list")[0][1]
        self.assertEqual(attrs["data-page"], "2")
        self.assertEqual(len(response.context["page_obj"]), 3)
        for notification in response.context["page_obj"]:
            self.assertContains(response, reverse("rescue:notification-open", args=(notification.pk,)))
        self.assertContains(response, "Trang 2 / 2")

    def test_two_sessions_receive_real_reports_and_feedback_without_reloading_admin_html(self):
        admin_client = Client(enforce_csrf_checks=True)
        member_client = Client(enforce_csrf_checks=True)
        admin_client.force_login(self.admin)
        member_client.force_login(self.member)
        state_url = reverse("rescue:notification-state")
        baseline_response = admin_client.get(state_url)
        self.assertEqual(baseline_response.status_code, 200)
        baseline = baseline_response.json()

        report_form = member_client.get(reverse("rescue:case-create"))
        self.assertEqual(report_form.status_code, 200)
        csrf_token = member_client.cookies["csrftoken"].value
        report_response = member_client.post(reverse("rescue:case-create"), {
            "csrfmiddlewaretoken": csrf_token,
            "title": "[QA-LIVE] Mèo bị thương cần tiếp nhận",
            "animal_type": RescueCase.AnimalType.CAT,
            "urgency": RescueCase.Urgency.HIGH,
            "description": "Mèo bị thương ở chân, đang nằm gần cổng chợ.",
            "address": "Cổng chợ Hàn, đường Trần Phú, Hải Châu, Đà Nẵng",
            "latitude": "16.054407", "longitude": "108.202167",
            "location_confirmed": "on",
            "contact_name": self.member.full_name, "contact_phone": "0901234567",
            "is_location_private": "on",
        })
        self.assertEqual(report_response.status_code, 302)
        reported_case = RescueCase.objects.get(title="[QA-LIVE] Mèo bị thương cần tiếp nhận")
        self.assertEqual(reported_case.reporter, self.member)
        report_notice = Notification.objects.get(
            recipient=self.admin, rescue_case=reported_case, kind=Notification.Kind.CASE_REPORTED,
        )

        report_state_response = admin_client.get(state_url, HTTP_IF_NONE_MATCH=baseline_response["ETag"])
        self.assertEqual(report_state_response.status_code, 200)
        self.assertEqual(report_state_response["Content-Type"], "application/json")
        report_state = report_state_response.json()
        self.assertEqual(report_state["total_count"], baseline["total_count"] + 1)
        self.assertEqual(report_state["unread_count"], baseline["unread_count"] + 1)
        self.assertEqual(report_state["latest_id"], report_notice.pk)
        item = next(item for item in report_state["items"] if item["id"] == report_notice.pk)
        self.assertEqual(item["title"], "Có tin báo cứu hộ mới")
        self.assertEqual(item["kind"], Notification.Kind.CASE_REPORTED)
        self.assertEqual(item["url"], reverse("rescue:case-detail", args=(reported_case.pk,)))

        feedback_response = member_client.post(reverse("rescue:case-list"), {
            "csrfmiddlewaretoken": csrf_token, "form_kind": "community_feedback",
            "name": self.member.full_name, "email": self.member.email,
            "category": CommunityFeedback.Category.FEATURE,
            "message": "[QA-LIVE] Mong dễ theo dõi phản hồi của đội cứu hộ.", "website": "",
        })
        self.assertEqual(feedback_response.status_code, 302)
        feedback = CommunityFeedback.objects.get(message="[QA-LIVE] Mong dễ theo dõi phản hồi của đội cứu hộ.")
        self.assertEqual(feedback.user, self.member)
        feedback_notice = Notification.objects.get(
            recipient=self.admin, kind=Notification.Kind.FEEDBACK_RECEIVED,
            target_url=reverse("admin:rescue_communityfeedback_change", args=(feedback.pk,)),
        )
        feedback_state_response = admin_client.get(
            state_url, HTTP_IF_NONE_MATCH=report_state_response["ETag"],
        )
        self.assertEqual(feedback_state_response.status_code, 200)
        feedback_state = feedback_state_response.json()
        self.assertEqual(feedback_state["total_count"], baseline["total_count"] + 2)
        self.assertEqual(feedback_state["unread_count"], baseline["unread_count"] + 2)
        self.assertEqual(feedback_state["latest_id"], feedback_notice.pk)
        newest = feedback_state["items"][0]
        self.assertEqual(newest["id"], feedback_notice.pk)
        self.assertEqual(newest["kind"], Notification.Kind.FEEDBACK_RECEIVED)
        self.assertEqual(newest["title"], "Có góp ý mới từ cộng đồng")

        for notice in (report_notice, feedback_notice):
            notice.refresh_from_db()
            self.assertFalse(notice.is_read)
            self.assertIsNone(notice.read_at)
        for user in (self.member, self.other_member):
            self.client.force_login(user)
            ordinary_state = self.client.get(state_url).json()
            self.assertNotIn(report_notice.pk, [item["id"] for item in ordinary_state["items"]])
            self.assertNotIn(Notification.Kind.CASE_REPORTED, [item["kind"] for item in ordinary_state["items"]])
            self.assertNotIn(feedback_notice.pk, [item["id"] for item in ordinary_state["items"]])

    def test_two_sessions_receive_support_message_and_unread_count_without_opening_inbox(self):
        admin_client = Client(enforce_csrf_checks=True)
        member_client = Client(enforce_csrf_checks=True)
        admin_client.force_login(self.admin)
        member_client.force_login(self.member)
        state_url = reverse("rescue:notification-state")
        initial_response = admin_client.get(state_url)
        self.assertEqual(initial_response.status_code, 200)
        initial = initial_response.json()
        member_client.get(reverse("rescue:knowledge-list"))
        response = member_client.post(reverse("support:chat-send"), {
            "csrfmiddlewaretoken": member_client.cookies["csrftoken"].value,
            "body": "[QA-LIVE] Nhờ admin kiểm tra giúp hồ sơ cứu hộ.",
        })
        self.assertEqual(response.status_code, 201)
        message = SupportMessage.objects.get(body="[QA-LIVE] Nhờ admin kiểm tra giúp hồ sơ cứu hộ.")
        notice = Notification.objects.filter(
            recipient=self.admin, kind=Notification.Kind.SUPPORT_MESSAGE,
        ).latest("pk")

        updated_response = admin_client.get(state_url, HTTP_IF_NONE_MATCH=initial_response["ETag"])
        self.assertEqual(updated_response.status_code, 200)
        updated = updated_response.json()
        self.assertEqual(updated["total_count"], initial["total_count"] + 1)
        self.assertEqual(updated["unread_count"], initial["unread_count"] + 1)
        self.assertEqual(updated["support_unread_count"], initial["support_unread_count"] + 1)
        self.assertEqual(updated["items"][0]["id"], notice.pk)
        self.assertEqual(updated["items"][0]["kind"], Notification.Kind.SUPPORT_MESSAGE)
        notice.refresh_from_db()
        message.refresh_from_db()
        self.assertFalse(notice.is_read)
        self.assertIsNone(notice.read_at)
        self.assertFalse(message.is_read_by_admin)
        self.assertNotContains(updated_response, message.body)
