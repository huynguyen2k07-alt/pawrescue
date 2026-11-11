"""Kiểm tra dữ liệu công khai và hồ sơ riêng bằng các tài khoản độc lập."""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import (
    CaseStatusHistory,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseImage,
    RescueCaseMessage,
    RescueUpdate,
    RescueUpdateImage,
)


@override_settings(SECURE_SSL_REDIRECT=False, MAPTILER_API_KEY="")
class PublicPrivacyReviewTests(TestCase):
    """Đổi URL hoặc đăng nhập tài khoản khác không được mở dữ liệu hiện trường."""

    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="privacy-admin@example.invalid", password="test-password",
        )
        cls.reporter = users.objects.create_user(
            email="privacy-reporter@example.invalid", password="test-password",
            full_name="Người báo tin riêng tư",
        )
        cls.assignee = users.objects.create_user(
            email="privacy-assignee@example.invalid", password="test-password",
            full_name="Nhân sự hiện trường", role=users.Role.MODERATOR,
        )
        cls.outsider = users.objects.create_user(
            email="privacy-outsider@example.invalid", password="test-password",
            full_name="Người dùng không liên quan",
        )
        cls.other_helper = users.objects.create_user(
            email="privacy-other-helper@example.invalid", password="test-password",
            full_name="Nhân sự chưa được phân công", role=users.Role.MODERATOR,
        )
        cls.secret_phone = "0987654321"
        cls.secret_address = "9127 Đường Hiện Trường Riêng, Đà Nẵng"
        cls.internal_note = "Ghi chú nội bộ AUDIT-NOTE-PRIVATE-7351."
        cls.internal_update = "Cập nhật hiện trường AUDIT-UPDATE-PRIVATE-4182."
        cls.case = RescueCase.objects.create(
            title="Mèo cần hỗ trợ",
            description="Nội dung hiện trường riêng AUDIT-DESCRIPTION-5931.",
            animal_type=RescueCase.AnimalType.CAT,
            animal_details="Dấu hiệu riêng AUDIT-ANIMAL-5913.",
            reporter=cls.reporter,
            status=RescueCase.Status.RESCUED,
            contact_name=cls.reporter.full_name,
            contact_phone=cls.secret_phone,
            address=cls.secret_address,
            latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            # Hồ sơ cũ từng cho công khai vẫn phải được bảo vệ theo chính sách mới.
            is_location_private=False,
        )
        cls.assignment = RescueAssignment.objects.create(
            rescue_case=cls.case, assignee=cls.assignee, assigned_by=cls.admin,
            notes="Chỉ dẫn riêng AUDIT-ASSIGNMENT-2948.",
        )
        CaseStatusHistory.objects.create(
            rescue_case=cls.case, from_status=RescueCase.Status.PENDING_REVIEW,
            to_status=RescueCase.Status.RESCUED, changed_by=cls.admin,
            note=cls.internal_note,
        )
        cls.update = RescueUpdate.objects.create(
            rescue_case=cls.case, author=cls.assignee, note=cls.internal_update,
        )
        # Chỉ gắn tên tệp: phép thử bị từ chối không cần đọc/tạo tệp trên đĩa.
        cls.image = RescueCaseImage.objects.create(
            rescue_case=cls.case, image="audit/incident-private.png",
        )
        cls.update_image = RescueUpdateImage.objects.create(
            update=cls.update, image="audit/update-private.png",
        )
        cls.private_message = RescueCaseMessage.objects.create(
            rescue_case=cls.case, sender=cls.admin, recipient=cls.assignee,
            body="Trao đổi nội bộ AUDIT-CHAT-8391.",
        )

    def client_for(self, user=None):
        client = Client()
        if user is not None:
            client.force_login(user)
        return client

    def detail_url(self):
        return reverse("rescue:case-detail", args=(self.case.pk,))

    def assert_no_contact(self, response):
        self.assertNotContains(response, self.secret_phone)
        self.assertNotContains(response, self.reporter.email)
        self.assertNotContains(response, self.reporter.full_name)

    def test_completed_phone_and_reporter_identity_hidden_from_public_and_other_users(self):
        for user in (None, self.outsider, self.other_helper):
            with self.subTest(user=user):
                self.assert_no_contact(self.client_for(user).get(self.detail_url()))

    def test_completed_exact_address_hidden_even_when_legacy_flag_is_public(self):
        for user in (None, self.outsider, self.other_helper):
            with self.subTest(user=user):
                response = self.client_for(user).get(self.detail_url())
                self.assertNotContains(response, self.secret_address)
                self.assertNotContains(response, "16.054407")
                self.assertNotContains(response, "108.202167")

    def test_completed_raw_description_and_animal_details_are_not_public(self):
        response = self.client.get(self.detail_url())
        self.assertNotContains(response, "AUDIT-DESCRIPTION-5931")
        self.assertNotContains(response, "AUDIT-ANIMAL-5913")

    def test_user_supplied_title_cannot_publish_contact_details(self):
        RescueCase.objects.filter(pk=self.case.pk).update(
            title=f"Mèo bị thương. Gọi {self.secret_phone} hoặc {self.reporter.email}. {self.secret_address}",
        )
        for url, params in (
            (self.detail_url(), {}),
            (reverse("rescue:case-list"), {"status": "rescued"}),
            (reverse("rescue:case-map"), {}),
        ):
            with self.subTest(url=url):
                response = self.client.get(url, params)
                self.assert_no_contact(response)
                self.assertNotContains(response, self.secret_address)

    def test_other_public_statuses_do_not_reveal_private_fields(self):
        for status in (
            RescueCase.Status.VERIFIED, RescueCase.Status.ASSIGNED,
            RescueCase.Status.IN_PROGRESS, RescueCase.Status.PENDING_REVIEW,
            RescueCase.Status.CLOSED, RescueCase.Status.CANCELLED,
        ):
            with self.subTest(status=status):
                RescueCase.objects.filter(pk=self.case.pk).update(status=status)
                response = self.client_for(self.outsider).get(self.detail_url())
                self.assert_no_contact(response)
                self.assertNotContains(response, self.secret_address)
                self.assertNotContains(response, self.internal_note)
                self.assertNotContains(response, self.internal_update)

    def test_private_views_do_not_allow_browser_or_proxy_storage(self):
        client = self.client_for(self.admin)
        for url in (self.detail_url(), reverse("rescue:case-map"), reverse("rescue:case-list")):
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers.get("Cache-Control", ""))
                self.assertIn("cookie", response.headers.get("Vary", "").lower())

    def test_raw_history_and_staff_identity_are_not_public(self):
        for user in (None, self.outsider, self.other_helper):
            with self.subTest(user=user):
                response = self.client_for(user).get(self.detail_url())
                self.assertNotContains(response, self.internal_note)
                self.assertNotContains(response, self.internal_update)
                self.assertNotContains(response, self.admin.email)
                self.assertNotContains(response, self.assignee.email)

    def test_authorized_participants_keep_contact_and_exact_location(self):
        for user in (self.admin, self.reporter, self.assignee):
            with self.subTest(user=user):
                response = self.client_for(user).get(self.detail_url())
                self.assertContains(response, self.secret_phone)
                self.assertContains(response, self.secret_address)
                self.assertContains(response, "16.054407")

    def test_public_completed_map_uses_approximate_location_and_no_contact(self):
        response = self.client.get(reverse("rescue:case-map"))
        marker = next(item for item in response.context["map_cases"] if item["id"] == self.case.pk)
        self.assertNotEqual(Decimal(str(marker["latitude"])), self.case.latitude)
        self.assertNotEqual(Decimal(str(marker["longitude"])), self.case.longitude)
        self.assertNotEqual(marker["address"], self.secret_address)
        self.assertTrue(marker["is_approximate"])
        self.assert_no_contact(response)
        self.assertNotContains(response, self.secret_address)

    def test_public_map_and_cards_do_not_publish_incident_image_urls(self):
        url = reverse("rescue:case-image", args=(self.image.pk,))
        for name in ("case-map", "case-list"):
            with self.subTest(page=name):
                response = self.client.get(reverse(f"rescue:{name}"), {"status": "rescued"})
                self.assertNotContains(response, url)

    def test_guessing_image_ids_does_not_bypass_private_case_access(self):
        with TemporaryDirectory(prefix="pawrescue-private-image-audit-") as directory:
            with override_settings(PRIVATE_RESCUE_MEDIA_ROOT=Path(directory)):
                image_directory = Path(directory) / "audit"
                image_directory.mkdir()
                for filename in ("incident-private.png", "update-private.png"):
                    (image_directory / filename).write_bytes(b"private-audit-fixture-image")
                for user in (None, self.outsider, self.other_helper):
                    for name, pk in (("case-image", self.image.pk), ("update-image", self.update_image.pk)):
                        with self.subTest(user=user, image=name):
                            response = self.client_for(user).get(reverse(f"rescue:{name}", args=(pk,)))
                            self.assertIn(response.status_code, (403, 404))

    def test_hidden_address_cannot_be_discovered_by_public_search(self):
        RescueCase.objects.filter(pk=self.case.pk).update(is_location_private=True)
        for user in (None, self.outsider):
            with self.subTest(user=user):
                response = self.client_for(user).get(reverse("rescue:case-list"), {
                    "status": "rescued", "q": "9127 Đường Hiện Trường Riêng",
                })
                self.assertNotIn(self.case.pk, [case.pk for case in response.context["page_obj"]])

    def test_authorized_search_can_find_own_exact_address(self):
        response = self.client_for(self.reporter).get(reverse("rescue:case-list"), {
            "status": "rescued", "q": "9127 Đường Hiện Trường Riêng",
        })
        self.assertIn(self.case.pk, [case.pk for case in response.context["page_obj"]])

    def test_revoked_helper_loses_contact_and_exact_location(self):
        RescueAssignment.objects.filter(pk=self.assignment.pk).update(is_active=False)
        response = self.client_for(self.assignee).get(self.detail_url())
        self.assert_no_contact(response)
        self.assertNotContains(response, self.secret_address)
        self.assertNotContains(response, "16.054407")

    def test_reporter_and_other_clients_cannot_open_private_coordination_messages(self):
        for user in (self.reporter, self.outsider, self.other_helper):
            with self.subTest(user=user):
                response = self.client_for(user).get(reverse("rescue:case-messages", args=(self.case.pk,)))
                self.assertIn(response.status_code, (403, 404))

    def test_reporter_does_not_read_internal_update_notes_or_staff_review(self):
        response = self.client_for(self.reporter).get(self.detail_url())
        self.assertContains(response, self.case.description)
        self.assertContains(response, reverse("rescue:case-image", args=(self.image.pk,)))
        self.assertNotContains(response, self.internal_note)
        self.assertNotContains(response, self.internal_update)
        self.assertNotContains(response, reverse("rescue:update-image", args=(self.update_image.pk,)))

    def test_reporter_status_notice_keeps_event_without_private_review_note(self):
        RescueCase.objects.filter(pk=self.case.pk).update(status=RescueCase.Status.VERIFIED)
        response = self.client_for(self.assignee).post(reverse("rescue:case-update-status", args=(self.case.pk,)), {
            "status": RescueCase.Status.PENDING_REVIEW, "note": self.internal_note,
        })
        self.assertEqual(response.status_code, 302)
        notice = Notification.objects.get(recipient=self.reporter, kind=Notification.Kind.STATUS_CHANGED)
        self.assertTrue(notice.message.strip())
        self.assertNotIn(self.internal_note, notice.message)
        self.assertTrue(self.case.status_history.filter(note=self.internal_note, to_status=RescueCase.Status.PENDING_REVIEW).exists())

    def test_reporter_update_notice_does_not_include_internal_field_journal(self):
        RescueCase.objects.filter(pk=self.case.pk).update(status=RescueCase.Status.VERIFIED)
        response = self.client_for(self.assignee).post(reverse("rescue:case-add-update", args=(self.case.pk,)), {
            "note": self.internal_update,
        })
        self.assertEqual(response.status_code, 302)
        notice = Notification.objects.get(recipient=self.reporter, kind=Notification.Kind.CASE_UPDATED)
        self.assertTrue(notice.message.strip())
        self.assertNotIn(self.internal_update, notice.message)
        self.assertTrue(self.case.updates.filter(note=self.internal_update, author=self.assignee).exists())

    def test_helper_only_sees_messages_addressed_to_them(self):
        RescueAssignment.objects.create(
            rescue_case=self.case, assignee=self.other_helper, assigned_by=self.admin,
        )
        private = RescueCaseMessage.objects.create(
            rescue_case=self.case, sender=self.admin, recipient=self.other_helper,
            body="Chỉ người nhận thứ hai AUDIT-SECOND-PRIVATE-9432.",
        )
        response = self.client_for(self.assignee).get(reverse("rescue:case-messages", args=(self.case.pk,)))
        self.assertContains(response, self.private_message.body)
        self.assertNotContains(response, private.body)

    def test_revoked_helper_does_not_keep_private_case_notifications(self):
        notification = Notification.objects.create(
            recipient=self.assignee, actor=self.admin, rescue_case=self.case,
            kind=Notification.Kind.CASE_MESSAGE,
            title="AUDIT-PRIVATE-NOTIFICATION-1836", message=self.secret_address,
            target_url=reverse("rescue:case-messages", args=(self.case.pk,)),
        )
        RescueAssignment.objects.filter(pk=self.assignment.pk).update(is_active=False)
        client = self.client_for(self.assignee)
        response = client.get(reverse("rescue:notification-list"))
        self.assertNotContains(response, notification.title)
        self.assertNotContains(response, self.secret_address)
        state = client.get(reverse("rescue:notification-state")).json()
        self.assertNotIn(notification.pk, [item["id"] for item in state["items"]])

    def test_other_user_cannot_mark_reporters_notification_read(self):
        notification = Notification.objects.create(
            recipient=self.reporter, actor=self.admin, rescue_case=self.case,
            kind=Notification.Kind.STATUS_CHANGED, title="Trạng thái mới", message="Đã cứu thành công.",
        )
        response = self.client_for(self.outsider).post(reverse("rescue:notification-open", args=(notification.pk,)))
        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
