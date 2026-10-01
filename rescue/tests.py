import base64
from decimal import Decimal
from io import StringIO
from tempfile import TemporaryDirectory

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from organizations.models import OrganizationMembership, RescueOrganization
from support.models import SupportConversation

from .admin import RescueCaseAdmin
from .models import (
    CaseStatusHistory,
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


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class CommunityHomepageTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            email="admin-feedback@example.com",
            password="test-password",
            full_name="Feedback Admin",
            is_staff=True,
        )
        self.superuser = get_user_model().objects.create_superuser(
            email="superuser-feedback@example.com",
            password="test-password",
            full_name="Feedback Superuser",
        )
        self.collaborator = get_user_model().objects.create_user(
            email="collaborator-feedback@example.com",
            password="test-password",
            full_name="Feedback Collaborator",
            role=get_user_model().Role.COLLABORATOR,
        )
        self.article = KnowledgeArticle.objects.create(
            title="Hướng dẫn cứu hộ an toàn",
            slug="huong-dan-cuu-ho-an-toan-test",
            category=KnowledgeArticle.Category.RESCUE,
            excerpt="Các bước an toàn ban đầu.",
            body="Giữ khoảng cách và liên hệ đội cứu hộ.",
            static_image_path="images/community/vet-kitten.jpg",
            source_name="Nguồn chuyên môn",
            source_url="https://example.com/source",
            is_featured=True,
        )
        self.contributor = ContributorProfile.objects.create(
            name="Nhóm hỗ trợ kiểm thử",
            role="Điều phối cộng đồng",
            bio="Hỗ trợ kết nối các ca cần giúp.",
            static_image_path="images/community/volunteer-dogs.jpg",
            photo_credit="Mia X / Pexels",
            photo_source_url="https://example.com/contributor-photo",
        )

    def test_homepage_shows_knowledge_contributors_and_feedback_form(self):
        response = self.client.get(reverse("rescue:case-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.article.title)
        self.assertContains(response, self.contributor.name)
        self.assertContains(response, "Ảnh: Mia X / Pexels")
        self.assertNotContains(response, self.contributor.photo_source_url)
        self.assertContains(response, "Gửi góp ý cho PawRescue")
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, "report-cta-icon")

    def test_homepage_uses_simple_status_tabs_and_rescue_archive(self):
        active_case = RescueCase.objects.create(
            title="Chó đang cần hỗ trợ",
            description="Cần đội cứu hộ đến kiểm tra.",
            animal_type=RescueCase.AnimalType.DOG,
            status=RescueCase.Status.VERIFIED,
            address="Quận 1",
        )
        rescued_case = RescueCase.objects.create(
            title="Mèo đã được cứu an toàn",
            description="Đã được đưa đến cơ sở thú y.",
            animal_type=RescueCase.AnimalType.CAT,
            status=RescueCase.Status.RESCUED,
            address="Quận 3",
        )
        cancelled_case = RescueCase.objects.create(
            title="Tin báo đã hủy",
            description="Tin báo trùng lặp.",
            animal_type=RescueCase.AnimalType.DOG,
            status=RescueCase.Status.CANCELLED,
            address="Quận 5",
        )

        response = self.client.get(reverse("rescue:case-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Đang cần cứu")
        self.assertContains(response, "Đã xác nhận")
        self.assertContains(response, "Đã cứu thành công")
        self.assertContains(response, "Đã hủy")
        self.assertContains(response, "Đã giải cứu thành công")
        self.assertNotContains(response, 'id="id_status"')
        self.assertContains(response, '?status=verified#rescue-cases')
        self.assertContains(response, 'action="/#rescue-cases"')
        self.assertEqual(
            [item.pk for item in response.context["page_obj"].object_list],
            [active_case.pk],
        )
        self.assertEqual(
            [item.pk for item in response.context["rescued_cases"]],
            [rescued_case.pk],
        )
        self.assertEqual(response.context["summary"]["rescued"], 1)

        rescued_response = self.client.get(
            reverse("rescue:case-list"),
            {"status": RescueCase.Status.RESCUED},
        )
        self.assertEqual(
            [item.pk for item in rescued_response.context["page_obj"].object_list],
            [rescued_case.pk],
        )
        self.assertContains(rescued_response, "Các ca đã cứu thành công")
        self.assertNotContains(rescued_response, "Kết quả được lưu lại")

        cancelled_response = self.client.get(
            reverse("rescue:case-list"),
            {"status": RescueCase.Status.CANCELLED},
        )
        self.assertEqual(
            [item.pk for item in cancelled_response.context["page_obj"].object_list],
            [cancelled_case.pk],
        )

    def test_guest_feedback_notifies_support_operators_only(self):
        response = self.client.post(
            reverse("rescue:case-list"),
            {
                "form_kind": "community_feedback",
                "name": "Người dùng thử",
                "email": "visitor@example.com",
                "category": CommunityFeedback.Category.FEATURE,
                "message": "Mong có thêm hướng dẫn chăm sóc sau cứu hộ.",
                "website": "",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('rescue:case-list')}#feedback",
            fetch_redirect_response=False,
        )
        feedback = CommunityFeedback.objects.get(email="visitor@example.com")
        self.assertEqual(feedback.status, CommunityFeedback.Status.NEW)
        recipients = set(
            Notification.objects.filter(
                kind=Notification.Kind.FEEDBACK_RECEIVED,
            ).values_list("recipient_id", flat=True)
        )
        self.assertEqual(
            recipients,
            {self.superuser.pk, self.collaborator.pk},
        )
        self.assertNotIn(self.staff.pk, recipients)

    def test_invalid_feedback_stays_on_homepage(self):
        response = self.client.post(
            reverse("rescue:case-list"),
            {
                "name": "Người dùng thử",
                "email": "khong-phai-email",
                "category": CommunityFeedback.Category.GENERAL,
                "message": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nhập địa chỉ email.")
        self.assertFalse(CommunityFeedback.objects.exists())

    def test_knowledge_list_and_detail_are_public(self):
        list_response = self.client.get(reverse("rescue:knowledge-list"))
        detail_response = self.client.get(
            reverse("rescue:knowledge-detail", args=(self.article.slug,))
        )

        self.assertContains(list_response, self.article.title)
        self.assertContains(detail_response, self.article.body)
        self.assertContains(detail_response, self.article.source_name)

    def test_homepage_exposes_three_watercolor_actions(self):
        response = self.client.get(reverse("rescue:case-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "images/brand/pawrescue-watercolor-actions.png",
        )
        self.assertContains(response, "Ủng hộ · Gây quỹ")
        self.assertContains(response, "Tìm chủ · Nhận nuôi")
        self.assertContains(response, "Các ca cứu hộ")

    def test_team_page_shows_active_contributors_in_display_order(self):
        second = ContributorProfile.objects.create(
            name="Nhóm thú y cộng đồng",
            role="Tư vấn sức khỏe",
            bio="Hỗ trợ thông tin chăm sóc ban đầu.",
        )
        ContributorProfile.objects.create(
            name="Nhóm tạm nghỉ",
            role="Hỗ trợ",
            bio="Không hiển thị lúc này.",
            is_active=False,
        )

        response = self.client.get(reverse("rescue:team"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.contributor.name)
        self.assertContains(response, second.name)
        self.assertContains(response, "Ảnh: Mia X / Pexels")
        self.assertNotContains(response, self.contributor.photo_source_url)
        self.assertNotContains(response, "Nhóm tạm nghỉ")
        contributors = list(response.context["contributors"])
        self.assertIn(self.contributor, contributors)
        self.assertIn(second, contributors)
        self.assertLess(
            contributors.index(self.contributor),
            contributors.index(second),
        )

    def test_knowledge_article_has_public_absolute_url(self):
        self.assertEqual(
            self.article.get_absolute_url(),
            reverse("rescue:knowledge-detail", args=(self.article.slug,)),
        )


class PublicContentSeedTests(TestCase):
    def test_seed_command_is_idempotent(self):
        from rescue.management.commands.seed_pawrescue_content import (
            ARTICLES,
            CONTRIBUTORS,
        )

        output = StringIO()
        call_command("seed_pawrescue_content", stdout=output)
        call_command("seed_pawrescue_content", stdout=output)

        article_slugs = [article["slug"] for article in ARTICLES]
        contributor_names = [profile["name"] for profile in CONTRIBUTORS]
        self.assertEqual(
            KnowledgeArticle.objects.filter(slug__in=article_slugs).count(),
            len(article_slugs),
        )
        self.assertEqual(
            ContributorProfile.objects.filter(
                name__in=contributor_names,
            ).count(),
            len(contributor_names),
        )
        self.assertIn("Đã đồng bộ", output.getvalue())

    def test_contributors_without_manual_order_are_appended(self):
        ContributorProfile.objects.all().delete()

        first = ContributorProfile.objects.create(
            name="Nhóm một",
            role="Điều phối",
            bio="Mô tả nhóm một.",
        )
        second = ContributorProfile.objects.create(
            name="Nhóm hai",
            role="Chăm sóc",
            bio="Mô tả nhóm hai.",
        )

        self.assertEqual(first.display_order, 1)
        self.assertEqual(second.display_order, 2)


class CommunityFeedbackAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            email="feedback-owner@example.com",
            password="test-password",
            full_name="Feedback Owner",
            is_staff=True,
            is_superuser=True,
        )
        self.sender = user_model.objects.create_user(
            email="feedback-sender@example.com",
            password="test-password",
            full_name="Người gửi góp ý",
        )
        self.feedback = CommunityFeedback.objects.create(
            user=self.sender,
            name=self.sender.full_name,
            email=self.sender.email,
            category=CommunityFeedback.Category.FEATURE,
            message="Tôi muốn theo dõi phản hồi này trực tiếp với quản trị viên.",
        )
        self.client.force_login(self.admin_user)

    def test_feedback_admin_inbox_shows_content_and_contact_actions(self):
        response = self.client.get(
            reverse("admin:rescue_communityfeedback_changelist")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hộp thư góp ý")
        self.assertContains(response, self.feedback.message)
        self.assertContains(response, "Trả lời Gmail")
        self.assertContains(response, "https://mail.google.com/mail/?")
        self.assertContains(response, "Mở chat nội bộ")
        self.assertEqual(response.context["feedback_counts"]["new"], 1)

    def test_opening_feedback_marks_it_reviewed_and_shows_full_message(self):
        response = self.client.get(
            reverse(
                "admin:rescue_communityfeedback_change",
                args=(self.feedback.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.feedback.refresh_from_db()
        self.assertEqual(
            self.feedback.status,
            CommunityFeedback.Status.REVIEWED,
        )
        self.assertIsNotNone(self.feedback.reviewed_at)
        self.assertContains(response, self.feedback.message)
        self.assertContains(response, "Trả lời qua Gmail")
        self.assertContains(response, "Mở chat với người gửi")

    def test_admin_can_open_internal_chat_from_feedback(self):
        response = self.client.post(
            reverse(
                "admin:rescue_communityfeedback_open_chat",
                args=(self.feedback.pk,),
            )
        )

        conversation = SupportConversation.objects.get(user=self.sender)
        expected_url = (
            reverse("support:inbox")
            + f"?conversation={conversation.pk}&feedback={self.feedback.pk}"
        )
        self.assertRedirects(
            response,
            expected_url,
            fetch_redirect_response=False,
        )
        inbox_response = self.client.get(expected_url)
        self.assertContains(inbox_response, f"góp ý #{self.feedback.pk}")
        self.assertContains(inbox_response, self.feedback.message)

    def test_admin_can_mark_feedback_closed(self):
        response = self.client.post(
            reverse(
                "admin:rescue_communityfeedback_quick_status",
                args=(self.feedback.pk, CommunityFeedback.Status.CLOSED),
            )
        )

        self.assertRedirects(
            response,
            reverse("admin:rescue_communityfeedback_changelist"),
        )
        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.status, CommunityFeedback.Status.CLOSED)
        self.assertIsNotNone(self.feedback.reviewed_at)


class AdminSiteSmokeTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            email="admin-smoke@example.com",
            password="test-password",
            full_name="Admin Smoke Test",
        )
        self.client.force_login(self.superuser)

    def test_registered_admin_lists_and_add_forms_load(self):
        request = RequestFactory().get("/admin/")
        request.user = self.superuser

        for model, model_admin in admin.site._registry.items():
            options = model._meta
            with self.subTest(model=options.label, page="changelist"):
                response = self.client.get(
                    reverse(
                        f"admin:{options.app_label}_{options.model_name}_changelist"
                    )
                )
                self.assertEqual(response.status_code, 200)

            if model_admin.has_add_permission(request):
                with self.subTest(model=options.label, page="add"):
                    response = self.client.get(
                        reverse(
                            f"admin:{options.app_label}_{options.model_name}_add"
                        )
                    )
                    self.assertEqual(response.status_code, 200)

    def test_admin_can_publish_edit_and_delete_knowledge_article(self):
        add_url = reverse("admin:rescue_knowledgearticle_add")
        article_data = {
            "title": "Hướng dẫn chăm sóc pet mới",
            "slug": "huong-dan-cham-soc-pet-moi",
            "category": KnowledgeArticle.Category.CARE,
            "excerpt": "Các bước chuẩn bị để pet làm quen với gia đình.",
            "body": "Chuẩn bị nơi nghỉ, nước sạch và lịch sinh hoạt ổn định.",
            "static_image_path": "",
            "image_credit": "",
            "image_source_url": "",
            "source_name": "PawRescue",
            "source_url": "",
            "is_published": "on",
            "published_at_0": timezone.localdate().isoformat(),
            "published_at_1": "09:00:00",
            "_save": "Lưu lại",
        }

        create_response = self.client.post(add_url, article_data)

        self.assertEqual(create_response.status_code, 302)
        article = KnowledgeArticle.objects.get(
            slug="huong-dan-cham-soc-pet-moi"
        )
        public_response = self.client.get(article.get_absolute_url())
        self.assertEqual(public_response.status_code, 200)
        self.assertContains(public_response, article.title)

        article_data["title"] = "Hướng dẫn chăm sóc pet mới tại nhà"
        article_data["_save"] = "Lưu lại"
        update_response = self.client.post(
            reverse(
                "admin:rescue_knowledgearticle_change",
                args=(article.pk,),
            ),
            article_data,
        )

        self.assertEqual(update_response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(
            article.title,
            "Hướng dẫn chăm sóc pet mới tại nhà",
        )
        self.assertContains(
            self.client.get(article.get_absolute_url()),
            article.title,
        )

        delete_response = self.client.post(
            reverse(
                "admin:rescue_knowledgearticle_delete",
                args=(article.pk,),
            ),
            {"post": "yes"},
        )

        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(KnowledgeArticle.objects.filter(pk=article.pk).exists())
        self.assertEqual(
            self.client.get(
                reverse(
                    "rescue:knowledge-detail",
                    args=(article.slug,),
                )
            ).status_code,
            404,
        )


class RescueCaseModelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.reporter = user_model.objects.create_user(
            email="reporter@example.com",
            password="test-password",
            full_name="Case Reporter",
        )
        self.volunteer = user_model.objects.create_user(
            email="volunteer@example.com",
            password="test-password",
            full_name="Rescue Volunteer",
        )
        self.organization = RescueOrganization.objects.create(
            name="Animal Friends Rescue",
            created_by=self.reporter,
            is_verified=True,
        )
        self.rescue_case = RescueCase.objects.create(
            title="Injured dog near the market",
            description="The dog cannot walk on its back leg.",
            animal_type=RescueCase.AnimalType.DOG,
            reporter=self.reporter,
            organization=self.organization,
            address="Central Market",
            contact_name="Case Reporter",
            contact_phone="0901234567",
        )

    def test_new_case_uses_expected_defaults(self):
        self.assertEqual(self.rescue_case.status, RescueCase.Status.REPORTED)
        self.assertEqual(self.rescue_case.urgency, RescueCase.Urgency.MEDIUM)

    def test_change_status_creates_history(self):
        history = self.rescue_case.change_status(
            RescueCase.Status.VERIFIED,
            changed_by=self.reporter,
            note="Location confirmed.",
        )

        self.rescue_case.refresh_from_db()
        self.assertEqual(self.rescue_case.status, RescueCase.Status.VERIFIED)
        self.assertEqual(history.from_status, RescueCase.Status.REPORTED)
        self.assertEqual(history.to_status, RescueCase.Status.VERIFIED)
        self.assertEqual(CaseStatusHistory.objects.count(), 1)

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.rescue_case.change_status("not-a-status")

    def test_admin_status_change_creates_history(self):
        request = RequestFactory().post("/admin/rescue/rescuecase/")
        request.user = self.reporter
        self.rescue_case.status = RescueCase.Status.CLOSED

        RescueCaseAdmin(RescueCase, AdminSite()).save_model(
            request,
            self.rescue_case,
            form=None,
            change=True,
        )

        self.rescue_case.refresh_from_db()
        history = CaseStatusHistory.objects.get()
        self.assertEqual(history.from_status, RescueCase.Status.REPORTED)
        self.assertEqual(history.to_status, RescueCase.Status.CLOSED)
        self.assertIsNotNone(self.rescue_case.closed_at)

    def test_admin_can_accept_case_with_one_click(self):
        self.rescue_case.organization = None
        self.rescue_case.save(update_fields=("organization",))
        admin_user = get_user_model().objects.create_user(
            email="accept-admin@example.com",
            password="test-password",
            full_name="Accept Admin",
            is_staff=True,
            is_superuser=True,
        )
        request = RequestFactory().post(
            "/admin/rescue/rescuecase/1/change/",
            {"_accept_case": "1"},
        )
        request.user = admin_user

        RescueCaseAdmin(RescueCase, AdminSite()).save_model(
            request,
            self.rescue_case,
            form=None,
            change=True,
        )

        self.rescue_case.refresh_from_db()
        self.assertEqual(self.rescue_case.organization.name, "PawRescue")
        self.assertEqual(self.rescue_case.status, RescueCase.Status.VERIFIED)
        self.assertTrue(self.rescue_case.organization.is_system)
        self.assertIsNone(self.rescue_case.organization.created_by)
        self.assertFalse(
            OrganizationMembership.objects.filter(
                organization=self.rescue_case.organization,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.reporter,
                rescue_case=self.rescue_case,
                kind=Notification.Kind.CASE_CLAIMED,
            ).exists()
        )

    def test_admin_cannot_accept_terminal_case(self):
        self.rescue_case.organization = None
        self.rescue_case.status = RescueCase.Status.CANCELLED
        self.rescue_case.save(update_fields=("organization", "status"))
        admin_user = get_user_model().objects.create_superuser(
            email="terminal-admin@example.com",
            password="test-password",
            full_name="Terminal Admin",
        )
        request = RequestFactory().post(
            "/admin/rescue/rescuecase/1/change/",
            {"_accept_case": "1"},
        )
        request.user = admin_user

        RescueCaseAdmin(RescueCase, AdminSite()).save_model(
            request,
            self.rescue_case,
            form=None,
            change=True,
        )

        self.rescue_case.refresh_from_db()
        self.assertIsNone(self.rescue_case.organization)
        self.assertEqual(self.rescue_case.status, RescueCase.Status.CANCELLED)
        self.assertFalse(request._pawrescue_accept_processed)

    def test_admin_change_page_shows_accept_button_for_unassigned_case(self):
        self.rescue_case.organization = None
        self.rescue_case.save(update_fields=("organization",))
        self.reporter.is_staff = True
        self.reporter.is_superuser = True
        self.reporter.save(update_fields=("is_staff", "is_superuser"))
        self.client.force_login(self.reporter)

        response = self.client.get(
            reverse(
                "admin:rescue_rescuecase_change",
                args=(self.rescue_case.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tiếp nhận bởi PawRescue")
        self.assertContains(response, 'name="_accept_case"')
        self.assertContains(response, "Nhắn người báo tin")
        self.assertContains(response, ">Xác nhận<", html=False)
        self.assertContains(response, ">Cứu thành công<", html=False)
        self.assertContains(response, ">Hủy ca<", html=False)
        self.assertContains(
            response,
            reverse("support:open-case-chat", args=(self.rescue_case.pk,)),
        )

    def test_admin_changelist_has_simple_workflow_and_rescue_history(self):
        self.reporter.is_staff = True
        self.reporter.is_superuser = True
        self.reporter.save(update_fields=("is_staff", "is_superuser"))
        self.client.force_login(self.reporter)
        changelist_url = reverse("admin:rescue_rescuecase_changelist")
        change_url = reverse(
            "admin:rescue_rescuecase_change",
            args=(self.rescue_case.pk,),
        )

        response = self.client.get(changelist_url)
        verify_url = reverse(
            "admin:rescue_rescuecase_quick_status",
            args=(self.rescue_case.pk, RescueCase.Status.VERIFIED),
        )
        rescued_url = reverse(
            "admin:rescue_rescuecase_quick_status",
            args=(self.rescue_case.pk, RescueCase.Status.RESCUED),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{change_url}"')
        self.assertContains(response, "Xử lý ca bằng một nút")
        self.assertContains(response, "Đã giải cứu thành công")
        self.assertContains(response, verify_url)
        self.assertContains(response, rescued_url)
        self.assertNotContains(response, 'name="form-0-status"')

        verify_response = self.client.post(verify_url)

        self.assertRedirects(verify_response, changelist_url)
        self.rescue_case.refresh_from_db()
        self.assertEqual(self.rescue_case.status, RescueCase.Status.VERIFIED)
        self.assertTrue(
            CaseStatusHistory.objects.filter(
                rescue_case=self.rescue_case,
                from_status=RescueCase.Status.REPORTED,
                to_status=RescueCase.Status.VERIFIED,
            ).exists()
        )

        rescued_response = self.client.post(rescued_url)

        self.assertRedirects(rescued_response, changelist_url)
        self.rescue_case.refresh_from_db()
        self.assertEqual(self.rescue_case.status, RescueCase.Status.RESCUED)
        self.assertIsNotNone(self.rescue_case.closed_at)
        final_response = self.client.get(changelist_url)
        self.assertEqual(final_response.context["rescue_counts"]["active"], 0)
        self.assertEqual(final_response.context["rescue_counts"]["rescued"], 1)
        self.assertContains(final_response, self.rescue_case.title)

    def test_admin_quick_cancel_records_cancelled_case(self):
        self.reporter.is_staff = True
        self.reporter.is_superuser = True
        self.reporter.save(update_fields=("is_staff", "is_superuser"))
        self.client.force_login(self.reporter)
        cancel_url = reverse(
            "admin:rescue_rescuecase_quick_status",
            args=(self.rescue_case.pk, RescueCase.Status.CANCELLED),
        )

        response = self.client.post(cancel_url)

        self.assertRedirects(
            response,
            reverse("admin:rescue_rescuecase_changelist"),
        )
        self.rescue_case.refresh_from_db()
        self.assertEqual(self.rescue_case.status, RescueCase.Status.CANCELLED)
        self.assertIsNotNone(self.rescue_case.closed_at)
        self.assertTrue(
            CaseStatusHistory.objects.filter(
                rescue_case=self.rescue_case,
                to_status=RescueCase.Status.CANCELLED,
            ).exists()
        )

    def test_admin_dashboard_record_count_updates_after_add_and_delete(self):
        self.reporter.is_staff = True
        self.reporter.is_superuser = True
        self.reporter.save(update_fields=("is_staff", "is_superuser"))
        self.client.force_login(self.reporter)

        def rescue_case_count(response):
            rescue_app = next(
                app
                for app in response.context["app_list"]
                if app["app_label"] == "rescue"
            )
            rescue_case_model = next(
                model
                for model in rescue_app["models"]
                if model["object_name"] == "RescueCase"
            )
            return rescue_case_model["record_count"]

        first_response = self.client.get(reverse("admin:index"))
        self.assertEqual(rescue_case_count(first_response), 1)
        self.assertContains(
            first_response,
            'data-model-count="rescue.rescuecase">1</strong>',
            html=False,
        )

        second_case = RescueCase.objects.create(
            title="Second rescue case",
            description="Created to verify the dashboard counter.",
            animal_type=RescueCase.AnimalType.CAT,
            address="District 1",
        )
        added_response = self.client.get(reverse("admin:index"))
        self.assertEqual(rescue_case_count(added_response), 2)

        second_case.delete()
        deleted_response = self.client.get(reverse("admin:index"))
        self.assertEqual(rescue_case_count(deleted_response), 1)

    def test_assignee_is_unique_per_case(self):
        RescueAssignment.objects.create(
            rescue_case=self.rescue_case,
            assignee=self.volunteer,
            assigned_by=self.reporter,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            RescueAssignment.objects.create(
                rescue_case=self.rescue_case,
                assignee=self.volunteer,
                assigned_by=self.reporter,
            )


class RescueCaseViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            email="manager@example.com",
            password="test-password",
            full_name="Rescue Manager",
        )
        self.volunteer = user_model.objects.create_user(
            email="volunteer-view@example.com",
            password="test-password",
            full_name="Rescue Volunteer",
        )
        self.reporter = user_model.objects.create_user(
            email="reporter-view@example.com",
            password="test-password",
            full_name="Concerned Reporter",
        )
        self.organization = RescueOrganization.objects.create(
            name="City Animal Rescue",
            created_by=self.manager,
            is_verified=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=OrganizationMembership.Role.OWNER,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.volunteer,
            role=OrganizationMembership.Role.VOLUNTEER,
        )
        self.rescue_case = RescueCase.objects.create(
            title="Cat stuck on a roof",
            description="The cat has been there since morning.",
            animal_type=RescueCase.AnimalType.CAT,
            urgency=RescueCase.Urgency.HIGH,
            address="District 1",
            contact_name="Concerned Neighbor",
            contact_phone="0912345678",
        )

    def test_case_list_and_detail_are_public(self):
        self.rescue_case.status = RescueCase.Status.VERIFIED
        self.rescue_case.save(update_fields=("status",))

        list_response = self.client.get(reverse("rescue:case-list"))
        detail_response = self.client.get(
            reverse("rescue:case-detail", args=(self.rescue_case.pk,))
        )

        self.assertContains(list_response, "Cat stuck on a roof")
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(detail_response, "0912345678")

    def test_case_create_requires_login(self):
        response = self.client.get(reverse("rescue:case-create"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('rescue:case-create')}",
        )

    def test_authenticated_user_can_create_case(self):
        user_model = get_user_model()
        superuser = user_model.objects.create_superuser(
            email="case-superuser@example.com",
            password="test-password",
            full_name="Case Superuser",
        )
        collaborator = user_model.objects.create_user(
            email="case-collaborator@example.com",
            password="test-password",
            full_name="Case Collaborator",
            role=user_model.Role.COLLABORATOR,
        )
        ordinary_staff = user_model.objects.create_user(
            email="case-staff@example.com",
            password="test-password",
            full_name="Case Staff",
            is_staff=True,
        )
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("rescue:case-create"),
            {
                "title": "Injured bird by the lake",
                "animal_type": RescueCase.AnimalType.BIRD,
                "animal_details": "Small brown bird",
                "urgency": RescueCase.Urgency.MEDIUM,
                "description": "One wing appears to be injured.",
                "address": "Hồ Thạc Gián, Thanh Khê, Đà Nẵng",
                "latitude": "16.060500",
                "longitude": "108.209800",
                "contact_name": "Rescue Manager",
                "contact_phone": "0900000000",
            },
        )

        created_case = RescueCase.objects.get(title="Injured bird by the lake")
        self.assertRedirects(
            response,
            reverse("rescue:case-detail", args=(created_case.pk,)),
        )
        self.assertEqual(created_case.reporter, self.manager)
        recipients = set(
            Notification.objects.filter(
                rescue_case=created_case,
                kind=Notification.Kind.CASE_REPORTED,
            ).values_list("recipient_id", flat=True)
        )
        self.assertEqual(recipients, {superuser.pk, collaborator.pk})
        self.assertNotIn(ordinary_staff.pk, recipients)

    def test_reported_case_is_private_but_available_to_triage_roles(self):
        self.rescue_case.latitude = Decimal("16.054407")
        self.rescue_case.longitude = Decimal("108.202167")
        self.rescue_case.is_location_private = True
        self.rescue_case.save(
            update_fields=("latitude", "longitude", "is_location_private")
        )
        detail_url = reverse("rescue:case-detail", args=(self.rescue_case.pk,))

        anonymous_list = self.client.get(reverse("rescue:case-list"))
        anonymous_map = self.client.get(reverse("rescue:case-map"))
        self.assertNotContains(anonymous_list, self.rescue_case.title)
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(anonymous_map.context["map_cases"], [])

        self.client.force_login(self.volunteer)
        self.assertNotContains(
            self.client.get(reverse("rescue:case-list")),
            self.rescue_case.title,
        )
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("rescue:case-map")).context["map_cases"],
            [],
        )

        self.rescue_case.reporter = self.reporter
        self.rescue_case.save(update_fields=("reporter",))
        self.client.force_login(self.reporter)
        reporter_detail = self.client.get(detail_url)
        self.assertEqual(reporter_detail.status_code, 200)
        self.assertContains(
            self.client.get(reverse("rescue:case-list")),
            self.rescue_case.title,
        )
        self.assertEqual(
            self.client.get(reverse("rescue:case-map")).context["map_cases"][0][
                "latitude"
            ],
            16.054407,
        )

        collaborator = get_user_model().objects.create_user(
            email="triage-collaborator@example.com",
            password="test-password",
            full_name="Triage Collaborator",
            role=get_user_model().Role.COLLABORATOR,
        )
        self.client.force_login(collaborator)
        collaborator_detail = self.client.get(detail_url)
        self.assertEqual(collaborator_detail.status_code, 200)
        self.assertTrue(collaborator_detail.context["can_view_contact"])
        self.assertTrue(collaborator_detail.context["can_view_location"])

        self.client.force_login(self.manager)
        manager_detail = self.client.get(detail_url)
        self.assertEqual(manager_detail.status_code, 200)
        self.assertTrue(manager_detail.context["can_claim"])

    def test_reported_case_image_requires_case_visibility(self):
        self.rescue_case.reporter = self.reporter
        self.rescue_case.save(update_fields=("reporter",))
        with TemporaryDirectory() as private_root, override_settings(
            PRIVATE_RESCUE_MEDIA_ROOT=private_root
        ):
            item = RescueCaseImage.objects.create(
                rescue_case=self.rescue_case,
                image=SimpleUploadedFile(
                    "private-scene.png",
                    PNG_1X1,
                    content_type="image/png",
                ),
                uploaded_by=self.reporter,
            )
            image_url = reverse("rescue:case-image", args=(item.pk,))

            with self.assertRaises(ValueError):
                _ = item.image.url
            self.assertEqual(self.client.get(image_url).status_code, 404)

            self.client.force_login(self.volunteer)
            self.assertEqual(self.client.get(image_url).status_code, 404)

            self.client.force_login(self.reporter)
            owner_response = self.client.get(image_url)
            self.assertEqual(owner_response.status_code, 200)
            self.assertEqual(
                b"".join(owner_response.streaming_content),
                PNG_1X1,
            )
            self.assertEqual(owner_response["Cache-Control"], "private, no-store")
            self.assertEqual(owner_response["X-Content-Type-Options"], "nosniff")

            self.rescue_case.status = RescueCase.Status.VERIFIED
            self.rescue_case.save(update_fields=("status",))
            self.client.logout()
            self.assertEqual(self.client.get(image_url).status_code, 200)

    def test_manager_can_claim_unassigned_case(self):
        self.rescue_case.reporter = self.reporter
        self.rescue_case.save(update_fields=("reporter",))
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("rescue:case-claim", args=(self.rescue_case.pk,)),
            {"organization": self.organization.pk},
        )

        self.assertRedirects(
            response,
            reverse("rescue:case-detail", args=(self.rescue_case.pk,)),
        )
        self.rescue_case.refresh_from_db()
        self.assertEqual(self.rescue_case.organization, self.organization)
        self.assertEqual(self.rescue_case.status, RescueCase.Status.VERIFIED)
        notification = Notification.objects.get(
            recipient=self.reporter,
            kind=Notification.Kind.CASE_CLAIMED,
        )
        self.assertEqual(notification.rescue_case, self.rescue_case)
        self.assertFalse(notification.is_read)

    def test_unverified_organization_cannot_claim_or_manage_case(self):
        self.organization.is_verified = False
        self.organization.save(update_fields=("is_verified", "updated_at"))
        self.rescue_case.organization = self.organization
        self.rescue_case.save(update_fields=("organization",))
        self.client.force_login(self.manager)

        status_response = self.client.post(
            reverse("rescue:case-update-status", args=(self.rescue_case.pk,)),
            {"status": RescueCase.Status.IN_PROGRESS},
        )
        self.rescue_case.organization = None
        self.rescue_case.save(update_fields=("organization",))
        claim_response = self.client.post(
            reverse("rescue:case-claim", args=(self.rescue_case.pk,)),
            {"organization": self.organization.pk},
        )

        self.assertEqual(status_response.status_code, 403)
        self.assertEqual(claim_response.status_code, 302)
        self.rescue_case.refresh_from_db()
        self.assertIsNone(self.rescue_case.organization)

    def test_unverified_organization_assignment_loses_private_case_access(self):
        self.rescue_case.organization = self.organization
        self.rescue_case.status = RescueCase.Status.VERIFIED
        self.rescue_case.contact_phone = "0999888777"
        self.rescue_case.is_location_private = True
        self.rescue_case.latitude = Decimal("16.054407")
        self.rescue_case.longitude = Decimal("108.202167")
        self.rescue_case.save(
            update_fields=(
                "organization",
                "status",
                "contact_phone",
                "is_location_private",
                "latitude",
                "longitude",
            )
        )
        RescueAssignment.objects.create(
            rescue_case=self.rescue_case,
            assignee=self.volunteer,
            assigned_by=self.manager,
        )
        self.organization.is_verified = False
        self.organization.save(update_fields=("is_verified", "updated_at"))
        self.client.force_login(self.volunteer)

        detail_response = self.client.get(
            reverse("rescue:case-detail", args=(self.rescue_case.pk,))
        )
        update_response = self.client.post(
            reverse("rescue:case-add-update", args=(self.rescue_case.pk,)),
            {"note": "Should not be accepted."},
        )

        self.assertNotContains(detail_response, "0999888777")
        self.assertTrue(detail_response.context["map_is_approximate"])
        self.assertEqual(update_response.status_code, 403)

    def test_manager_cannot_claim_terminal_case(self):
        self.rescue_case.status = RescueCase.Status.CANCELLED
        self.rescue_case.save(update_fields=("status",))
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("rescue:case-claim", args=(self.rescue_case.pk,)),
            {"organization": self.organization.pk},
        )

        self.assertEqual(response.status_code, 302)
        self.rescue_case.refresh_from_db()
        self.assertIsNone(self.rescue_case.organization)

    def test_manager_can_assign_member_and_update_status(self):
        self.rescue_case.reporter = self.reporter
        self.rescue_case.organization = self.organization
        self.rescue_case.save(update_fields=("reporter", "organization"))
        self.client.force_login(self.manager)

        assignment_response = self.client.post(
            reverse("rescue:case-assign", args=(self.rescue_case.pk,)),
            {"assignee": self.volunteer.pk, "notes": "Bring a ladder."},
        )
        status_response = self.client.post(
            reverse("rescue:case-update-status", args=(self.rescue_case.pk,)),
            {
                "status": RescueCase.Status.IN_PROGRESS,
                "note": "Team is on the way.",
            },
        )

        self.assertEqual(assignment_response.status_code, 302)
        self.assertEqual(status_response.status_code, 302)
        self.assertTrue(
            RescueAssignment.objects.filter(
                rescue_case=self.rescue_case,
                assignee=self.volunteer,
            ).exists()
        )
        self.rescue_case.refresh_from_db()
        self.assertEqual(self.rescue_case.status, RescueCase.Status.IN_PROGRESS)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.volunteer,
                kind=Notification.Kind.CASE_ASSIGNED,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.reporter,
                kind=Notification.Kind.STATUS_CHANGED,
            ).exists()
        )

    def test_volunteer_cannot_update_status(self):
        self.rescue_case.organization = self.organization
        self.rescue_case.save(update_fields=("organization",))
        self.client.force_login(self.volunteer)

        response = self.client.post(
            reverse("rescue:case-update-status", args=(self.rescue_case.pk,)),
            {"status": RescueCase.Status.CLOSED},
        )

        self.assertEqual(response.status_code, 403)

    def test_map_page_uses_approximate_location_for_private_case(self):
        self.rescue_case.latitude = Decimal("16.054407")
        self.rescue_case.longitude = Decimal("108.202167")
        self.rescue_case.is_location_private = True
        self.rescue_case.status = RescueCase.Status.VERIFIED
        self.rescue_case.save(
            update_fields=(
                "latitude",
                "longitude",
                "is_location_private",
                "status",
            )
        )

        response = self.client.get(reverse("rescue:case-map"))

        self.assertEqual(response.status_code, 200)
        map_case = response.context["map_cases"][0]
        self.assertEqual(map_case["latitude"], 16.05)
        self.assertEqual(map_case["longitude"], 108.2)
        self.assertTrue(map_case["is_approximate"])
        self.assertNotContains(response, "District 1")

    def test_reporter_sees_exact_private_location(self):
        self.rescue_case.reporter = self.manager
        self.rescue_case.latitude = Decimal("16.054407")
        self.rescue_case.longitude = Decimal("108.202167")
        self.rescue_case.is_location_private = True
        self.rescue_case.save(
            update_fields=(
                "reporter",
                "latitude",
                "longitude",
                "is_location_private",
            )
        )
        self.client.force_login(self.manager)

        response = self.client.get(reverse("rescue:case-map"))

        map_case = response.context["map_cases"][0]
        self.assertEqual(map_case["latitude"], 16.054407)
        self.assertEqual(map_case["longitude"], 108.202167)
        self.assertFalse(map_case["is_approximate"])

    def test_cancelled_case_is_not_shown_on_map(self):
        self.rescue_case.latitude = Decimal("16.054407")
        self.rescue_case.longitude = Decimal("108.202167")
        self.rescue_case.status = RescueCase.Status.CANCELLED
        self.rescue_case.save(
            update_fields=("latitude", "longitude", "status")
        )

        response = self.client.get(reverse("rescue:case-map"))

        self.assertEqual(response.context["map_cases"], [])

    def test_case_outside_da_nang_is_not_shown_on_map(self):
        self.rescue_case.latitude = Decimal("10.776889")
        self.rescue_case.longitude = Decimal("106.700806")
        self.rescue_case.save(update_fields=("latitude", "longitude"))

        response = self.client.get(reverse("rescue:case-map"))

        self.assertEqual(response.context["map_cases"], [])

    def test_case_form_rejects_location_outside_da_nang(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("rescue:case-create"),
            {
                "title": "Tin báo ngoài khu vực",
                "animal_type": RescueCase.AnimalType.DOG,
                "urgency": RescueCase.Urgency.MEDIUM,
                "description": "Kiểm tra giới hạn phạm vi hoạt động.",
                "address": "Quận 1, TP Hồ Chí Minh",
                "latitude": "10.776889",
                "longitude": "106.700806",
                "contact_name": "Rescue Manager",
                "contact_phone": "0900000000",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chỉ tiếp nhận ca trong phạm vi Đà Nẵng")
        self.assertFalse(
            RescueCase.objects.filter(title="Tin báo ngoài khu vực").exists()
        )

    def test_case_form_contains_location_picker_and_privacy_option(self):
        self.client.force_login(self.manager)

        response = self.client.get(reverse("rescue:case-create"))

        self.assertContains(response, 'id="location-picker-map"')
        self.assertContains(response, 'name="is_location_private"')
        self.assertContains(response, "phạm vi Đà Nẵng")

    @override_settings(MAPTILER_API_KEY="test-maptiler-key")
    def test_map_page_exposes_configured_maptiler_key(self):
        response = self.client.get(reverse("rescue:case-map"))

        self.assertContains(response, 'data-maptiler-key="test-maptiler-key"')

    def test_notification_page_shows_unread_badge_and_filter(self):
        Notification.objects.create(
            recipient=self.reporter,
            actor=self.manager,
            rescue_case=self.rescue_case,
            kind=Notification.Kind.STATUS_CHANGED,
            title="Trạng thái ca cứu hộ đã thay đổi",
            message="Đội cứu hộ đang trên đường đến.",
        )
        self.client.force_login(self.reporter)

        response = self.client.get(reverse("rescue:notification-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trạng thái ca cứu hộ đã thay đổi")
        self.assertContains(response, "notification-badge")
        self.assertEqual(response.context["unread_count"], 1)

    def test_open_notification_marks_it_read_and_redirects_to_case(self):
        self.rescue_case.reporter = self.reporter
        self.rescue_case.save(update_fields=("reporter",))
        notification = Notification.objects.create(
            recipient=self.reporter,
            actor=self.manager,
            rescue_case=self.rescue_case,
            kind=Notification.Kind.CASE_CLAIMED,
            title="Ca cứu hộ đã được tiếp nhận",
        )
        self.client.force_login(self.reporter)

        response = self.client.post(
            reverse("rescue:notification-open", args=(notification.pk,))
        )

        self.assertRedirects(
            response,
            reverse("rescue:case-detail", args=(self.rescue_case.pk,)),
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_user_cannot_open_another_users_notification(self):
        notification = Notification.objects.create(
            recipient=self.reporter,
            rescue_case=self.rescue_case,
            kind=Notification.Kind.CASE_ASSIGNED,
            title="Ca cứu hộ đã được phân công",
        )
        self.client.force_login(self.volunteer)

        response = self.client.post(
            reverse("rescue:notification-open", args=(notification.pk,))
        )

        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_all_read_only_updates_current_users_notifications(self):
        own_notification = Notification.objects.create(
            recipient=self.reporter,
            rescue_case=self.rescue_case,
            kind=Notification.Kind.STATUS_CHANGED,
            title="Cập nhật cho người báo tin",
        )
        other_notification = Notification.objects.create(
            recipient=self.volunteer,
            rescue_case=self.rescue_case,
            kind=Notification.Kind.STATUS_CHANGED,
            title="Cập nhật cho tình nguyện viên",
        )
        self.client.force_login(self.reporter)

        response = self.client.post(reverse("rescue:notification-read-all"))

        self.assertRedirects(response, reverse("rescue:notification-list"))
        own_notification.refresh_from_db()
        other_notification.refresh_from_db()
        self.assertTrue(own_notification.is_read)
        self.assertFalse(other_notification.is_read)

    def test_manager_can_post_rescue_update_with_image_and_notify_reporter(self):
        self.rescue_case.reporter = self.reporter
        self.rescue_case.organization = self.organization
        self.rescue_case.save(update_fields=("reporter", "organization"))
        self.client.force_login(self.manager)
        uploaded_image = SimpleUploadedFile(
            "rescue-progress.png",
            PNG_1X1,
            content_type="image/png",
        )

        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            response = self.client.post(
                reverse("rescue:case-add-update", args=(self.rescue_case.pk,)),
                {
                    "note": "Đã đưa mèo xuống an toàn và kiểm tra sơ bộ.",
                    "images": uploaded_image,
                },
            )

            self.assertRedirects(
                response,
                reverse("rescue:case-detail", args=(self.rescue_case.pk,)),
            )
            rescue_update = RescueUpdate.objects.get()
            self.assertEqual(rescue_update.author, self.manager)
            self.assertEqual(RescueUpdateImage.objects.count(), 1)

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.reporter,
                kind=Notification.Kind.CASE_UPDATED,
                rescue_case=self.rescue_case,
            ).exists()
        )

    def test_assigned_volunteer_can_post_rescue_update(self):
        self.rescue_case.reporter = self.reporter
        self.rescue_case.organization = self.organization
        self.rescue_case.save(update_fields=("reporter", "organization"))
        RescueAssignment.objects.create(
            rescue_case=self.rescue_case,
            assignee=self.volunteer,
            assigned_by=self.manager,
        )
        self.client.force_login(self.volunteer)

        response = self.client.post(
            reverse("rescue:case-add-update", args=(self.rescue_case.pk,)),
            {"note": "Đội đã đến hiện trường và đang tiếp cận."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            RescueUpdate.objects.filter(
                rescue_case=self.rescue_case,
                author=self.volunteer,
            ).exists()
        )

    def test_unassigned_user_cannot_post_rescue_update(self):
        self.rescue_case.reporter = self.reporter
        self.rescue_case.organization = self.organization
        self.rescue_case.save(update_fields=("reporter", "organization"))
        self.client.force_login(self.reporter)

        response = self.client.post(
            reverse("rescue:case-add-update", args=(self.rescue_case.pk,)),
            {"note": "Nội dung không được phép đăng."},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(RescueUpdate.objects.exists())

    def test_rescue_updates_appear_in_public_case_timeline(self):
        self.rescue_case.status = RescueCase.Status.VERIFIED
        self.rescue_case.save(update_fields=("status",))
        RescueUpdate.objects.create(
            rescue_case=self.rescue_case,
            author=self.manager,
            note="Đã sơ cứu và đưa động vật tới phòng khám.",
        )

        response = self.client.get(
            reverse("rescue:case-detail", args=(self.rescue_case.pk,))
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cập nhật hiện trường")
        self.assertContains(
            response,
            "Đã sơ cứu và đưa động vật tới phòng khám.",
        )
