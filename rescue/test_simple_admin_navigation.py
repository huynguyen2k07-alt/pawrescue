from decimal import Decimal
from html.parser import HTMLParser

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from config.admin_site import RescueAdminSite
from donations.models import Donation
from organizations.models import RescueOrganization
from support.models import SupportConversation, SupportMessage

from .models import KnowledgeArticle, RescueCase
from .templatetags.pawrescue_admin import pawrescue_admin_dashboard


class NavigationLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.inside_navigation = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and attrs.get("class") == "paw-operational-nav":
            self.inside_navigation = True
        elif tag == "a" and self.inside_navigation:
            self.links.append(attrs)

    def handle_endtag(self, tag):
        if tag == "div" and self.inside_navigation:
            self.inside_navigation = False


@override_settings(SECURE_SSL_REDIRECT=False)
class SimpleAdminNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_superuser(
            email="simple-admin@example.com", password="test-password", full_name="Quản trị chính",
        )
        cls.operator = users.objects.create_user(
            email="simple-operator@example.com", password="test-password",
            full_name="Nhân sự hỗ trợ", role=users.Role.COLLABORATOR, is_staff=True,
        )
        cls.other_operator = users.objects.create_user(
            email="simple-other-operator@example.com", password="test-password",
            full_name="Nhân sự khác", role=users.Role.COLLABORATOR, is_staff=True,
        )
        cls.account_viewer = users.objects.create_user(
            email="simple-account-viewer@example.com", password="test-password",
            full_name="Người xem tài khoản", is_staff=True,
        )
        cls.account_viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label="accounts", codename="view_user",
        ))
        cls.staff = users.objects.create_user(
            email="simple-staff@example.com", password="test-password", is_staff=True,
        )
        cls.member = users.objects.create_user(
            email="simple-reporter@example.com", password="test-password", full_name="Người báo tin",
        )
        cls.case = RescueCase.objects.create(
            title="Tin báo riêng chờ xác minh", description="Động vật cần hỗ trợ.",
            reporter=cls.member, animal_type=RescueCase.AnimalType.CAT,
            address="123 Nguyễn Văn Linh, Hải Châu, Đà Nẵng",
            latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            is_location_private=True, urgency=RescueCase.Urgency.CRITICAL,
        )
        cls.completed_case = RescueCase.objects.create(
            title="Ca đã chốt để lưu hồ sơ", description="Đã xử lý xong.",
            animal_type=RescueCase.AnimalType.DOG, address="Đà Nẵng",
            status=RescueCase.Status.RESCUED,
        )
        cls.unassigned_conversation = SupportConversation.objects.create(
            user=cls.member, subject="Tin chưa phân công",
        )
        cls.own_conversation = SupportConversation.objects.create(
            user=cls.account_viewer, assigned_to=cls.operator, subject="Tin của người phụ trách",
        )
        cls.other_conversation = SupportConversation.objects.create(
            user=cls.staff, assigned_to=cls.other_operator, subject="Nội dung riêng của nhân sự khác",
        )
        cls.closed_conversation = SupportConversation.objects.create(
            user=cls.owner, status=SupportConversation.Status.CLOSED,
            subject="Hội thoại đã đóng",
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def request_for(self, user, path="/admin/"):
        request = RequestFactory().get(path)
        request.user = user
        return request

    def overview_for(self, response):
        return pawrescue_admin_dashboard({
            "request": response.wsgi_request,
            "user": response.wsgi_request.user,
        }, response.context["app_list"])

    def test_default_site_keeps_registered_models_while_listing_only_essential_models(self):
        self.assertIsInstance(admin.site, RescueAdminSite)
        for model in (RescueCase, RescueOrganization, Donation, KnowledgeArticle, SupportMessage):
            self.assertIn(model, admin.site._registry)
        app_list = admin.site.get_app_list(self.request_for(self.owner))
        self.assertEqual([
            item["model"]._meta.label_lower for app in app_list for item in app["models"]
        ], ["rescue.rescuecase", "accounts.user", "organizations.rescueorganization"])
        self.assertEqual([app["name"] for app in app_list], ["Cứu hộ", "Nhân sự", "Đơn vị tiếp nhận"])

    def test_four_primary_links_are_real_anchors_for_opening_in_another_tab(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        navigation = response.context["operational_nav"]
        self.assertEqual([item["key"] for item in navigation], ["cases", "inbox", "personnel", "organizations"])
        parser = NavigationLinks()
        parser.feed(response.content.decode())
        self.assertEqual([link["href"] for link in parser.links], [item["url"] for item in navigation])
        for link in parser.links:
            self.assertNotIn("onclick", link)
            self.assertFalse(link["href"].startswith(("#", "javascript:")))

    def test_dashboard_links_directly_to_case_workspace_and_hides_unused_modules(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, f'href="{reverse("rescue:case-detail", args=(self.case.pk,))}"')
        self.assertNotContains(response, reverse("admin:rescue_rescuecase_change", args=(self.case.pk,)))
        self.assertNotContains(response, self.completed_case.title)
        self.assertContains(response, 'data-model-count="rescue.rescuecase">2</strong>')
        for name in (
            "admin:donations_donation_changelist",
            "admin:rescue_knowledgearticle_changelist",
            "admin:rescue_notification_changelist",
            "admin:rescue_rescueassignment_changelist",
            "admin:support_supportmessage_changelist",
            "admin:support_supportattachment_changelist",
            "admin:organizations_organizationmembership_changelist",
            "admin:auth_group_changelist",
        ):
            self.assertNotContains(response, f'href="{reverse(name)}"')
        overview = self.overview_for(response)
        self.assertEqual(overview["case_count"], 2)
        self.assertEqual(overview["reported_case_count"], 1)
        self.assertEqual(overview["completed_case_count"], 1)

    def test_hidden_admin_routes_still_use_existing_permissions_and_data(self):
        for name in (
            "admin:donations_donation_changelist",
            "admin:rescue_knowledgearticle_changelist",
            "admin:support_supportmessage_changelist",
            "admin:auth_group_changelist",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertTrue(RescueCase.objects.filter(pk=self.case.pk).exists())

    def test_processing_metric_includes_cases_waiting_for_main_admin_approval(self):
        self.case.status = RescueCase.Status.PENDING_REVIEW
        self.case.save(update_fields=("status",))
        dashboard = self.client.get(reverse("admin:index"))
        overview = self.overview_for(dashboard)
        self.assertEqual(overview["in_progress_case_count"], 1)
        processing_url = (
            reverse("admin:rescue_rescuecase_changelist")
            + "?status__in=verified,assigned,in_progress,pending_review"
        )
        self.assertContains(dashboard, f'href="{processing_url}"')
        listing = self.client.get(processing_url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.context["cl"].result_count, 1)
        self.assertEqual([case.pk for case in listing.context["cl"].result_list], [self.case.pk])

    def test_app_index_also_hides_unrelated_models(self):
        self.assertEqual(admin.site.get_app_list(self.request_for(self.owner), "donations"), [])
        rescue_apps = admin.site.get_app_list(self.request_for(self.owner), "rescue")
        self.assertEqual([item["object_name"] for item in rescue_apps[0]["models"]], ["RescueCase"])

    def test_operator_sees_only_own_or_unassigned_pending_conversations(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual([item["key"] for item in response.context["operational_nav"]], ["inbox"])
        overview = self.overview_for(response)
        self.assertEqual(overview["pending_support_count"], 2)
        self.assertEqual(set(item.pk for item in overview["pending_conversations"]), {
            self.unassigned_conversation.pk, self.own_conversation.pk,
        })
        self.assertContains(response, self.own_conversation.subject)
        self.assertNotContains(response, self.other_conversation.subject)
        self.assertNotContains(response, self.case.title)
        self.assertNotContains(response, self.case.address)
        self.assertEqual(overview["case_count"], 0)

    def test_superuser_can_see_all_pending_conversations(self):
        response = self.client.get(reverse("admin:index"))
        overview = self.overview_for(response)
        self.assertEqual(overview["pending_support_count"], 3)
        self.assertContains(response, self.other_conversation.subject)
        self.assertNotContains(response, self.closed_conversation.subject)

    def test_account_viewer_gets_personnel_link_without_case_or_chat_access(self):
        self.client.force_login(self.account_viewer)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual([item["key"] for item in response.context["operational_nav"]], ["personnel"])
        self.assertNotContains(response, self.case.title)
        self.assertNotContains(response, self.own_conversation.subject)
        model_info = response.context["app_list"][0]["models"][0]
        self.assertEqual(model_info["record_count"], get_user_model().objects.filter(
            is_staff=False, is_superuser=False,
        ).count() + 1)

    def test_staff_without_operational_permissions_gets_no_navigation_or_private_data(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.context["operational_nav"], [])
        self.assertNotContains(response, self.case.title)
        self.assertNotContains(response, self.other_conversation.subject)
        self.assertContains(response, "Tài khoản chưa được cấp quyền điều phối")

    def test_non_staff_member_cannot_open_admin_dashboard(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)
        self.assertNotContains(response, self.case.title, status_code=302)
