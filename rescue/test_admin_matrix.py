"""Kiểm thử biểu mẫu quản trị bằng hai phiên riêng của quản trị viên và thành viên."""

import base64
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from support.models import SupportConversation

from .models import (
    CommunityFeedback,
    ContributorProfile,
    KnowledgeArticle,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseImage,
    RescueUpdate,
    RescueUpdateImage,
)


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@override_settings(SECURE_SSL_REDIRECT=False)
class RescueAdminMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_superuser(
            email="matrix-owner@example.com", password="test-password", full_name="Quản trị chính"
        )
        cls.member = users.objects.create_user(
            email="matrix-member@example.com", password="test-password", full_name="Người báo tin"
        )
        cls.operator = users.objects.create_user(
            email="matrix-operator@example.com", password="test-password",
            full_name="Người được phân công", role=users.Role.COLLABORATOR,
        )
        cls.staff = users.objects.create_user(
            email="matrix-staff@example.com", password="test-password",
            full_name="Nhân viên thường", is_staff=True,
        )
        cls.case = RescueCase.objects.create(
            title="Mèo bị thương tại Nguyễn Văn Linh",
            animal_type=RescueCase.AnimalType.CAT, description="Cần sơ cứu chân bị thương.",
            address="123 Nguyễn Văn Linh, Hải Châu, Đà Nẵng", reporter=cls.member,
            latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            contact_name=cls.member.full_name, contact_phone="0901234567",
        )
        cls.assignment = RescueAssignment.objects.create(
            rescue_case=cls.case, assignee=cls.operator,
            assigned_by=cls.owner, notes="Mang lồng vận chuyển.",
        )
        cls.update = RescueUpdate.objects.create(
            rescue_case=cls.case, author=cls.operator, note="Đã tới hiện trường."
        )
        cls.feedback = CommunityFeedback.objects.create(
            user=cls.member, name=cls.member.full_name, email=cls.member.email,
            category=CommunityFeedback.Category.PROBLEM,
            message="Cần hỗ trợ kiểm tra vị trí trên bản đồ.",
        )
        cls.profile = ContributorProfile.objects.create(
            name="Nhân sự kiểm thử", role="Điều phối", bio="Đội hỗ trợ cứu hộ.",
        )
        cls.article = KnowledgeArticle.objects.create(
            title="Sơ cứu mèo bị thương", slug="so-cuu-meo-kiem-thu",
            category=KnowledgeArticle.Category.RESCUE,
            excerpt="Các bước giữ an toàn.", body="Liên hệ bác sĩ thú y.",
        )
        cls.notification = Notification.objects.create(
            recipient=cls.member, rescue_case=cls.case,
            kind=Notification.Kind.CASE_UPDATED, title="Có cập nhật", message="Đã tới nơi.",
        )

    def setUp(self):
        self.media_dir = TemporaryDirectory(prefix="paw-admin-matrix-")
        self.addCleanup(self.media_dir.cleanup)
        self.media_settings = override_settings(
            MEDIA_ROOT=Path(self.media_dir.name) / "public",
            PRIVATE_RESCUE_MEDIA_ROOT=Path(self.media_dir.name) / "private",
        )
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.client.force_login(self.owner)
        self.member_client = Client()
        self.member_client.force_login(self.member)

    def admin_url(self, model, action="changelist", obj=None):
        name = f"admin:{model._meta.app_label}_{model._meta.model_name}_{action}"
        return reverse(name, args=(obj.pk,)) if obj is not None else reverse(name)

    def case_payload(self, **changes):
        payload = {
            "title": self.case.title, "description": self.case.description,
            "animal_type": self.case.animal_type, "urgency": self.case.urgency,
            "address": self.case.address, "reporter": self.member.pk,
            "contact_name": self.member.full_name, "contact_phone": "0901234567",
            "latitude": "16.054407", "longitude": "108.202167", "organization": "",
            "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "1000",
            "assignments-TOTAL_FORMS": "0", "assignments-INITIAL_FORMS": "0",
            "status_history-TOTAL_FORMS": "0", "status_history-INITIAL_FORMS": "0",
            "updates-TOTAL_FORMS": "0", "updates-INITIAL_FORMS": "0", "_save": "1",
        }
        payload.update(changes)
        return payload

    def article_payload(self, **changes):
        payload = {
            "title": "Hướng dẫn kiểm thử cứu hộ", "slug": "huong-dan-kiem-thu",
            "category": KnowledgeArticle.Category.RESCUE,
            "excerpt": "Chuẩn bị phương tiện an toàn.", "body": "Liên hệ đội điều phối.",
            "published_at_0": timezone.localdate().isoformat(), "published_at_1": "09:00:00",
            "is_published": "on", "_save": "1",
        }
        payload.update(changes)
        return payload

    def profile_payload(self, **changes):
        payload = {
            "name": "Cộng sự kiểm thử mới", "role": "Bác sĩ thú y",
            "bio": "Tiếp nhận động vật cần sơ cứu.", "display_order": "5", "is_active": "on", "_save": "1",
        }
        payload.update(changes)
        return payload

    def test_admin_all_rescue_lists_and_existing_records_render(self):
        records = (
            (RescueCase, self.case), (RescueAssignment, self.assignment),
            (RescueUpdate, self.update), (CommunityFeedback, self.feedback),
            (ContributorProfile, self.profile), (KnowledgeArticle, self.article),
            (Notification, self.notification),
        )
        for model, obj in records:
            with self.subTest(model=model.__name__):
                self.assertEqual(self.client.get(self.admin_url(model)).status_code, 200)
                change_url = self.admin_url(model, "change", obj)
                if model is RescueCase:
                    self.assertRedirects(
                        self.client.get(change_url),
                        reverse("rescue:case-detail", args=(obj.pk,)),
                    )
                    change_url += "?edit=1"
                self.assertEqual(self.client.get(change_url).status_code, 200)

    def test_ordinary_member_cannot_read_or_submit_any_rescue_admin_form(self):
        for model in (RescueCase, RescueCaseImage, RescueAssignment, RescueUpdate,
                      CommunityFeedback, KnowledgeArticle, ContributorProfile, Notification):
            for method in ("get", "post"):
                with self.subTest(model=model.__name__, method=method):
                    response = getattr(self.member_client, method)(self.admin_url(model))
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.url.startswith(reverse("admin:login")))

    def test_staff_with_all_model_permissions_cannot_access_private_rescue_records(self):
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="rescue"))
        self.client.force_login(self.staff)
        for model, obj in ((RescueCase, self.case), (CommunityFeedback, self.feedback),
                           (RescueAssignment, self.assignment), (RescueUpdate, self.update),
                           (Notification, self.notification)):
            for action in ("changelist", "change", "delete"):
                with self.subTest(model=model.__name__, action=action):
                    url = self.admin_url(model, action, None if action == "changelist" else obj)
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_editorial_permissions_still_allow_staff_to_manage_public_content(self):
        self.staff.user_permissions.set(Permission.objects.filter(
            content_type__app_label="rescue",
            content_type__model__in=("knowledgearticle", "contributorprofile"),
        ))
        self.client.force_login(self.staff)
        for model, obj in ((KnowledgeArticle, self.article), (ContributorProfile, self.profile)):
            with self.subTest(model=model.__name__):
                self.assertEqual(self.client.get(self.admin_url(model)).status_code, 200)
                self.assertEqual(self.client.get(self.admin_url(model, "change", obj)).status_code, 200)

    def test_admin_creates_edits_and_deletes_map_pinned_report(self):
        response = self.client.post(self.admin_url(RescueCase, "add"), self.case_payload(title="Ca do admin tạo"))
        self.assertEqual(response.status_code, 302)
        case = RescueCase.objects.get(title="Ca do admin tạo")
        self.assertEqual(case.latitude, Decimal("16.054407"))
        self.assertEqual(case.reporter, self.member)
        response = self.client.post(
            self.admin_url(RescueCase, "change", case), self.case_payload(title="Địa chỉ đã kiểm tra")
        )
        self.assertEqual(response.status_code, 302)
        case.refresh_from_db()
        self.assertEqual(case.title, "Địa chỉ đã kiểm tra")
        self.assertEqual(self.member_client.get(reverse("rescue:case-detail", args=(case.pk,))).status_code, 200)
        response = self.client.post(self.admin_url(RescueCase, "delete", case), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RescueCase.objects.filter(pk=case.pk).exists())

    def test_admin_report_rejects_missing_partial_invalid_or_outside_map_pin(self):
        for latitude, longitude in (("", ""), ("16.05", ""), ("", "108.2"),
                                    ("abc", "108.2"), ("91", "108.2"), ("10.7", "106.6")):
            with self.subTest(latitude=latitude, longitude=longitude):
                response = self.client.post(
                    self.admin_url(RescueCase, "add"),
                    self.case_payload(title="Ca vị trí không hợp lệ", latitude=latitude, longitude=longitude),
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["adminform"].form.errors)
        self.assertFalse(RescueCase.objects.filter(title="Ca vị trí không hợp lệ").exists())

    def test_legacy_report_without_map_pin_can_be_corrected_in_admin(self):
        self.case.latitude = None
        self.case.longitude = None
        self.case.save(update_fields=("latitude", "longitude"))
        response = self.client.post(
            self.admin_url(RescueCase, "change", self.case),
            self.case_payload(title="Sửa hồ sơ cũ", latitude="", longitude=""),
        )
        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.title, "Sửa hồ sơ cũ")

    def test_valid_report_pin_cannot_be_removed_in_admin(self):
        response = self.client.post(
            self.admin_url(RescueCase, "change", self.case), self.case_payload(latitude="", longitude="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("latitude", response.context["adminform"].form.errors)
        self.case.refresh_from_db()
        self.assertEqual(self.case.latitude, Decimal("16.054407"))

    def test_posted_status_cannot_bypass_readonly_status_or_review(self):
        response = self.client.post(
            self.admin_url(RescueCase, "change", self.case), self.case_payload(status=RescueCase.Status.CLOSED)
        )
        self.assertEqual(response.status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.REPORTED)
        self.assertFalse(self.case.status_history.exists())

    def test_readonly_case_inlines_cannot_forge_assignments_history_or_field_reports(self):
        payload = self.case_payload()
        payload.update({
            "assignments-TOTAL_FORMS": "1", "assignments-0-assignee": self.member.pk,
            "assignments-0-assigned_by": self.owner.pk, "assignments-0-notes": "Phân công giả",
            "status_history-TOTAL_FORMS": "1", "status_history-0-to_status": "closed",
            "updates-TOTAL_FORMS": "1", "updates-0-note": "Nhật ký giả", "updates-0-author": self.owner.pk,
        })
        response = self.client.post(self.admin_url(RescueCase, "change", self.case), payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.case.assignments.count(), 1)
        self.assertEqual(self.case.updates.count(), 1)
        self.assertFalse(self.case.status_history.exists())

    def test_accept_bulk_action_is_idempotent_and_notifies_reporter(self):
        url = self.admin_url(RescueCase)
        payload = {"action": "accept_selected_cases", "_selected_action": [self.case.pk]}
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, RescueCase.Status.VERIFIED)
        self.assertTrue(self.case.organization.is_system)
        self.assertEqual(self.case.status_history.count(), 1)
        self.assertEqual(Notification.objects.filter(
            rescue_case=self.case, recipient=self.member, kind=Notification.Kind.CASE_CLAIMED,
        ).count(), 1)

    def test_assignment_records_cannot_be_forged_modified_or_deleted_in_admin(self):
        for action in ("add", "change", "delete"):
            obj = None if action == "add" else self.assignment
            with self.subTest(action=action):
                response = self.client.post(self.admin_url(RescueAssignment, action, obj), {"post": "yes"})
                self.assertEqual(response.status_code, 403)
        self.assertTrue(RescueAssignment.objects.filter(pk=self.assignment.pk, is_active=True).exists())
        response = self.client.get(self.admin_url(RescueAssignment, "change", self.assignment))
        self.assertContains(response, reverse("rescue:case-detail", args=(self.case.pk,)))

    def test_case_admin_search_and_status_filter_return_expected_records(self):
        other = RescueCase.objects.create(
            title="Chó đã giải cứu", description="Hoàn tất", animal_type=RescueCase.AnimalType.DOG,
            address="Đà Nẵng", status=RescueCase.Status.RESCUED,
        )
        for query in ({"q": "Nguyễn Văn Linh"}, {"status__exact": RescueCase.Status.REPORTED}):
            with self.subTest(query=query):
                response = self.client.get(self.admin_url(RescueCase), query)
                self.assertEqual(list(response.context["cl"].queryset), [self.case])
        self.assertTrue(RescueCase.objects.filter(pk=other.pk).exists())

    def test_admin_contributor_crud_changes_public_team(self):
        response = self.client.post(self.admin_url(ContributorProfile, "add"), self.profile_payload())
        self.assertEqual(response.status_code, 302)
        profile = ContributorProfile.objects.get(name="Cộng sự kiểm thử mới")
        self.assertContains(self.member_client.get(reverse("rescue:team")), profile.name)
        response = self.client.post(
            self.admin_url(ContributorProfile, "change", profile), self.profile_payload(name="Bác sĩ đã cập nhật")
        )
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.member_client.get(reverse("rescue:team")), "Bác sĩ đã cập nhật")
        self.client.post(self.admin_url(ContributorProfile, "change", profile), self.profile_payload(is_active=""))
        self.assertNotContains(self.member_client.get(reverse("rescue:team")), "Cộng sự kiểm thử mới")
        self.assertEqual(self.client.post(self.admin_url(ContributorProfile, "delete", profile), {"post": "yes"}).status_code, 302)
        self.assertFalse(ContributorProfile.objects.filter(pk=profile.pk).exists())

    def test_contributor_search_filter_and_invalid_display_order(self):
        response = self.client.get(self.admin_url(ContributorProfile), {"q": "kiểm thử", "is_active__exact": "1"})
        self.assertEqual(list(response.context["cl"].queryset), [self.profile])
        response = self.client.post(self.admin_url(ContributorProfile, "add"), self.profile_payload(display_order="-1"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("display_order", response.context["adminform"].form.errors)

    def test_contributor_list_editable_saves_order_and_visibility(self):
        response = self.client.post(self.admin_url(ContributorProfile), {
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-id": self.profile.pk, "form-0-display_order": "12", "_save": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.display_order, 12)
        self.assertFalse(self.profile.is_active)
        self.assertNotContains(self.member_client.get(reverse("rescue:team")), self.profile.name)

    def test_admin_knowledge_crud_publish_unpublish_and_search(self):
        response = self.client.post(self.admin_url(KnowledgeArticle, "add"), self.article_payload())
        self.assertEqual(response.status_code, 302)
        article = KnowledgeArticle.objects.get(slug="huong-dan-kiem-thu")
        self.assertContains(self.member_client.get(article.get_absolute_url()), article.title)
        response = self.client.post(
            self.admin_url(KnowledgeArticle, "change", article), self.article_payload(title="Hướng dẫn đã cập nhật", is_published="")
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.member_client.get(article.get_absolute_url()).status_code, 404)
        response = self.client.get(self.admin_url(KnowledgeArticle), {"q": "đã cập nhật", "is_published__exact": "0"})
        self.assertEqual(list(response.context["cl"].queryset), [article])
        self.assertEqual(self.client.post(self.admin_url(KnowledgeArticle, "delete", article), {"post": "yes"}).status_code, 302)
        self.assertFalse(KnowledgeArticle.objects.filter(pk=article.pk).exists())

    def test_duplicate_article_slug_and_invalid_url_show_form_errors(self):
        response = self.client.post(
            self.admin_url(KnowledgeArticle, "add"),
            self.article_payload(slug=self.article.slug, source_url="javascript:alert(1)"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("slug", response.context["adminform"].form.errors)
        self.assertIn("source_url", response.context["adminform"].form.errors)

    def test_article_list_editable_can_feature_and_unpublish(self):
        response = self.client.post(self.admin_url(KnowledgeArticle), {
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000",
            "form-0-id": self.article.pk, "form-0-is_featured": "on", "_save": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertTrue(self.article.is_featured)
        self.assertFalse(self.article.is_published)
        self.assertEqual(self.member_client.get(self.article.get_absolute_url()).status_code, 404)

    def test_invalid_images_are_form_errors_for_all_editable_admin_uploads(self):
        cases = (
            (KnowledgeArticle, "cover_image", self.article_payload()),
            (ContributorProfile, "photo", self.profile_payload()),
            (RescueCaseImage, "image", {"rescue_case": self.case.pk, "caption": "Ảnh lỗi"}),
        )
        for model, field, payload in cases:
            with self.subTest(model=model.__name__):
                payload = {**payload, field: SimpleUploadedFile("not-an-image.jpg", b"invalid bytes", content_type="image/jpeg")}
                response = self.client.post(self.admin_url(model, "add"), payload)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["adminform"].form.errors)
                self.assertContains(response, "Nội dung tệp không phải")
        self.assertFalse(list(Path(self.media_dir.name).rglob("*.jpg")))

    def test_admin_image_size_mismatch_and_truncated_content_are_form_errors(self):
        for name, content in (("wrong.jpg", PNG), ("truncated.png", PNG[:25]), ("large.jpg", b"x" * (5 * 1024 * 1024 + 1))):
            with self.subTest(name=name):
                response = self.client.post(
                    self.admin_url(ContributorProfile, "add"),
                    self.profile_payload(photo=SimpleUploadedFile(name, content)),
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("photo", response.context["adminform"].form.errors)

    def test_invalid_case_inline_image_does_not_create_case_or_write_file(self):
        payload = self.case_payload(title="Ca ảnh lỗi")
        payload.update({
            "images-TOTAL_FORMS": "1", "images-0-caption": "Ảnh hiện trường",
            "images-0-image": SimpleUploadedFile("broken.jpg", b"bad", content_type="image/jpeg"),
        })
        response = self.client.post(self.admin_url(RescueCase, "add"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("image", response.context["inline_admin_formsets"][0].formset.forms[0].errors)
        self.assertFalse(RescueCase.objects.filter(title="Ca ảnh lỗi").exists())
        self.assertFalse(list(Path(self.media_dir.name).rglob("*.jpg")))

    def test_valid_images_save_and_existing_private_images_render_and_edit(self):
        response = self.client.post(
            self.admin_url(RescueCaseImage, "add"),
            {"rescue_case": self.case.pk, "caption": "Ảnh hợp lệ", "uploaded_by": self.owner.pk,
             "image": SimpleUploadedFile("scene.png", PNG, content_type="image/png")},
        )
        self.assertEqual(response.status_code, 302)
        image = RescueCaseImage.objects.get(rescue_case=self.case)
        self.assertEqual(self.client.get(self.admin_url(RescueCaseImage, "change", image)).status_code, 200)
        response = self.client.get(self.admin_url(RescueCase, "change", self.case) + "?edit=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("rescue:case-image", args=(image.pk,)))
        response = self.client.post(
            self.admin_url(RescueCaseImage, "change", image),
            {"rescue_case": self.case.pk, "caption": "Đã sửa chú thích", "uploaded_by": self.owner.pk},
        )
        self.assertEqual(response.status_code, 302)
        image.refresh_from_db()
        self.assertEqual(image.caption, "Đã sửa chú thích")
        self.assertEqual(self.member_client.get(reverse("rescue:case-image", args=(image.pk,))).status_code, 200)

    def test_valid_public_admin_images_save_without_rejecting_existing_file(self):
        for model, field, payload, lookup in (
            (KnowledgeArticle, "cover_image", self.article_payload(), {"slug": "huong-dan-kiem-thu"}),
            (ContributorProfile, "photo", self.profile_payload(), {"name": "Cộng sự kiểm thử mới"}),
        ):
            with self.subTest(model=model.__name__):
                response = self.client.post(
                    self.admin_url(model, "add"), {**payload, field: SimpleUploadedFile("valid.png", PNG)}
                )
                self.assertEqual(response.status_code, 302)
                obj = model.objects.get(**lookup)
                self.assertTrue(getattr(obj, field).name.endswith(".png"))
                response = self.client.post(self.admin_url(model, "change", obj), payload)
                self.assertEqual(response.status_code, 302)

    def test_field_update_with_private_photo_is_readable_in_admin(self):
        image = RescueUpdateImage.objects.create(
            update=self.update, image=SimpleUploadedFile("field.png", PNG, content_type="image/png")
        )
        response = self.client.get(self.admin_url(RescueUpdate, "change", self.update))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("rescue:update-image", args=(image.pk,)))

    def test_member_feedback_request_is_available_to_main_admin(self):
        response = self.member_client.post(reverse("rescue:case-list"), {
            "name": self.member.full_name, "email": self.member.email,
            "category": CommunityFeedback.Category.FEATURE, "message": "Kiểm thử góp ý từ tài khoản phụ.",
        })
        self.assertEqual(response.status_code, 302)
        feedback = CommunityFeedback.objects.get(message="Kiểm thử góp ý từ tài khoản phụ.")
        self.assertEqual(feedback.user, self.member)
        self.assertContains(self.client.get(self.admin_url(CommunityFeedback)), feedback.message)
        self.assertTrue(Notification.objects.filter(
            recipient=self.owner, kind=Notification.Kind.FEEDBACK_RECEIVED,
        ).exists())

    def test_feedback_search_filter_applies_to_inbox_cards_and_table(self):
        CommunityFeedback.objects.create(
            name="Người gửi khác", email="other@example.com", message="Nội dung khác.",
            category=CommunityFeedback.Category.GENERAL, status=CommunityFeedback.Status.CLOSED,
        )
        for query in ({"q": "bản đồ"}, {"status__exact": "new"}, {"category__exact": "problem"}):
            with self.subTest(query=query):
                response = self.client.get(self.admin_url(CommunityFeedback), query)
                self.assertEqual(list(response.context["cl"].queryset), [self.feedback])
                self.assertEqual(response.context["feedback_items"], [self.feedback])
                self.assertEqual(response.context["feedback_counts"], {"new": 1, "reviewed": 0, "closed": 0})

    def test_feedback_status_edit_preserves_original_user_content_and_can_be_deleted(self):
        response = self.client.post(self.admin_url(CommunityFeedback, "change", self.feedback), {
            "status": CommunityFeedback.Status.CLOSED, "name": "Giả mạo", "message": "Sửa trái phép", "_save": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.message, "Cần hỗ trợ kiểm tra vị trí trên bản đồ.")
        self.assertEqual(self.feedback.status, CommunityFeedback.Status.CLOSED)
        self.assertIsNotNone(self.feedback.reviewed_at)
        self.client.post(self.admin_url(CommunityFeedback, "change", self.feedback), {"status": "new", "_save": "1"})
        self.feedback.refresh_from_db()
        self.assertIsNone(self.feedback.reviewed_at)
        self.assertEqual(self.client.post(self.admin_url(CommunityFeedback, "delete", self.feedback), {"post": "yes"}).status_code, 302)
        self.assertFalse(CommunityFeedback.objects.filter(pk=self.feedback.pk).exists())

    def test_feedback_chat_reuses_active_conversation_without_duplicate_or_reassignment(self):
        conversation = SupportConversation.objects.create(user=self.member, assigned_to=self.owner, subject="Đang hỗ trợ")
        url = reverse("admin:rescue_communityfeedback_open_chat", args=(self.feedback.pk,))
        self.assertEqual(self.client.get(url).status_code, 405)
        for _ in range(2):
            response = self.client.post(url)
            self.assertEqual(response.status_code, 302)
        self.assertEqual(SupportConversation.objects.filter(user=self.member).count(), 1)
        self.assertIn(f"conversation={conversation.pk}", response.url)

    def test_guest_feedback_open_chat_does_not_create_conversation(self):
        self.feedback.user = None
        self.feedback.save(update_fields=("user",))
        response = self.client.post(reverse("admin:rescue_communityfeedback_open_chat", args=(self.feedback.pk,)))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupportConversation.objects.exists())

    def test_staff_cannot_use_feedback_custom_actions_despite_model_permissions(self):
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="rescue"))
        self.client.force_login(self.staff)
        for url in (
            reverse("admin:rescue_communityfeedback_open_chat", args=(self.feedback.pk,)),
            reverse("admin:rescue_communityfeedback_quick_status", args=(self.feedback.pk, "closed")),
            reverse("admin:rescue_rescuecase_quick_status", args=(self.case.pk, "verified")),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 403)
        self.feedback.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(self.feedback.status, CommunityFeedback.Status.NEW)
        self.assertEqual(self.case.status, RescueCase.Status.REPORTED)

    def test_invalid_quick_status_and_missing_records_return_404_without_changes(self):
        for url in (
            reverse("admin:rescue_communityfeedback_quick_status", args=(self.feedback.pk, "invalid")),
            reverse("admin:rescue_communityfeedback_quick_status", args=(999999, "closed")),
            reverse("admin:rescue_rescuecase_quick_status", args=(self.case.pk, "invalid")),
            reverse("admin:rescue_rescuecase_quick_status", args=(999999, "verified")),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 404)

    def test_delete_case_cascades_only_its_workflow_records(self):
        other_case = RescueCase.objects.create(
            title="Hồ sơ khác", description="Giữ nguyên", animal_type="dog", address="Đà Nẵng", reporter=self.member,
        )
        self.assertEqual(self.client.post(self.admin_url(RescueCase, "delete", self.case), {"post": "yes"}).status_code, 302)
        self.assertFalse(RescueAssignment.objects.filter(pk=self.assignment.pk).exists())
        self.assertFalse(RescueUpdate.objects.filter(pk=self.update.pk).exists())
        self.assertFalse(Notification.objects.filter(pk=self.notification.pk).exists())
        self.assertTrue(RescueCase.objects.filter(pk=other_case.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.member.pk).exists())
        self.assertTrue(CommunityFeedback.objects.filter(pk=self.feedback.pk).exists())

    def test_case_bulk_delete_cascades_assignments_without_enabling_direct_delete(self):
        response = self.client.post(self.admin_url(RescueCase), {
            "action": "delete_selected", "_selected_action": [self.case.pk], "post": "yes",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RescueCase.objects.filter(pk=self.case.pk).exists())
        self.assertFalse(RescueAssignment.objects.filter(pk=self.assignment.pk).exists())
