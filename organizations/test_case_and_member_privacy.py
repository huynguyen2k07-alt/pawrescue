"""Thành viên tổ chức không tự có quyền đọc hồ sơ riêng hoặc email của đồng đội."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from donations.forms import FundraisingCampaignForm
from rescue.models import RescueAssignment, RescueCase, RescueCaseImage

from .models import OrganizationMembership, RescueOrganization


@override_settings(SECURE_SSL_REDIRECT=False)
class OrganizationCaseAndMemberPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="org-privacy-admin@example.com", password="test-password", full_name="Admin chính",
        )
        cls.owner = users.objects.create_user(
            email="org-privacy-owner@example.com", password="test-password", full_name="Chủ trung tâm",
        )
        cls.manager = users.objects.create_user(
            email="org-privacy-manager@example.com", password="test-password", full_name="Điều phối viên",
        )
        cls.member = users.objects.create_user(
            email="org-privacy-member@example.com", password="test-password", full_name="Tình nguyện viên",
        )
        cls.no_name_member = users.objects.create_user(
            email="org-privacy-private-noname@example.com", password="test-password", full_name="",
        )
        cls.reporter = users.objects.create_user(
            email="org-privacy-reporter@example.com", password="test-password", full_name="Người báo riêng",
        )
        cls.organization = RescueOrganization.objects.create(
            name="Trung tâm có thành viên", created_by=cls.owner, is_verified=True,
            email="org-privacy-business@example.com",
        )
        for user, role in (
            (cls.owner, OrganizationMembership.Role.OWNER),
            (cls.manager, OrganizationMembership.Role.MANAGER),
            (cls.member, OrganizationMembership.Role.VOLUNTEER),
            (cls.no_name_member, OrganizationMembership.Role.VOLUNTEER),
        ):
            OrganizationMembership.objects.create(organization=cls.organization, user=user, role=role)
        cls.case = RescueCase.objects.create(
            organization=cls.organization, reporter=cls.reporter,
            animal_type=RescueCase.AnimalType.CAT, status=RescueCase.Status.VERIFIED,
            title="sensitive-case-title-organisation", description="sensitive-case-description-organisation",
            address="sensitive-exact-address-organisation", contact_name="sensitive-contact-organisation",
            contact_phone="0905555666",
        )
        cls.image = RescueCaseImage(
            rescue_case=cls.case, image="rescue_cases/private-org-photo.png", caption="sensitive-photo-caption",
        )
        RescueCaseImage.objects.bulk_create([cls.image])

    def org_urls(self):
        return (
            reverse("organizations:dashboard"),
            reverse("organizations:organization-detail", args=(self.organization.pk,)),
        )

    def campaign_data(self):
        return {
            "organization": self.organization.pk, "rescue_case": self.case.pk,
            "title": "Hỗ trợ ca thử", "description": "Kế hoạch hỗ trợ công khai",
            "target_amount": "100000", "status": "draft",
        }

    def test_unassigned_org_owner_manager_and_member_get_safe_case_cards(self):
        for user in (self.owner, self.manager, self.member):
            self.client.force_login(user)
            for url in self.org_urls():
                with self.subTest(user=user.pk, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, f"Ca cứu hộ Mèo #{self.case.pk}")
                    for value in (
                        self.case.title, self.case.description, self.case.address,
                        self.case.contact_name, self.case.contact_phone, self.reporter.email,
                        reverse("rescue:case-image", args=(self.image.pk,)),
                    ):
                        self.assertNotContains(response, value)
                    self.assertEqual(response.context["cases"][0].contact_phone, "")
                    self.assertIsNone(response.context["cases"][0].reporter)
                    self.assertIn("no-store", response["Cache-Control"])
                    self.assertIn("Cookie", response["Vary"])

    def test_assigned_org_member_and_admin_keep_authorized_case_cards(self):
        RescueAssignment.objects.create(rescue_case=self.case, assignee=self.manager, assigned_by=self.admin)
        for user in (self.manager, self.admin):
            self.client.force_login(user)
            for url in self.org_urls():
                with self.subTest(user=user.pk, url=url):
                    response = self.client.get(url)
                    self.assertContains(response, self.case.title)
                    self.assertContains(response, reverse("rescue:case-image", args=(self.image.pk,)))
                    self.assertEqual(response.context["cases"][0], self.case)

    def test_other_member_emails_are_hidden_even_when_name_is_missing(self):
        detail_url = reverse("organizations:organization-detail", args=(self.organization.pk,))
        for viewer in (self.manager, self.member):
            self.client.force_login(viewer)
            response = self.client.get(detail_url)
            self.assertContains(response, viewer.email)
            self.assertContains(response, "Thành viên")
            for account in (self.owner, self.manager, self.member, self.no_name_member):
                if account != viewer:
                    self.assertNotContains(response, account.email)
            for row in response.context["memberships"]:
                self.assertFalse(hasattr(row, "user"))
                if row.user_id != viewer.pk:
                    self.assertEqual(row.display_email, "")

    def test_owner_and_main_admin_can_see_member_contact_emails(self):
        url = reverse("organizations:organization-detail", args=(self.organization.pk,))
        for user in (self.owner, self.admin):
            self.client.force_login(user)
            response = self.client.get(url)
            for account in (self.owner, self.manager, self.member, self.no_name_member):
                self.assertContains(response, account.email)

    def test_denied_private_organization_page_is_not_cacheable(self):
        self.client.force_login(self.reporter)
        response = self.client.get(reverse("organizations:organization-detail", args=(self.organization.pk,)))
        self.assertEqual(response.status_code, 403)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])

    def test_campaign_case_choices_do_not_leak_unassigned_case_title(self):
        for user in (self.owner, self.manager):
            with self.subTest(user=user.pk):
                form = FundraisingCampaignForm(user=user)
                self.assertFalse(form.fields["rescue_case"].queryset.filter(pk=self.case.pk).exists())
                self.assertNotIn(self.case.title, form.as_p())
                bound = FundraisingCampaignForm(self.campaign_data(), user=user)
                self.assertFalse(bound.is_valid())
                self.assertIn("rescue_case", bound.errors)
                self.assertNotIn(self.case.title, bound.as_p())

    def test_campaign_case_choices_allow_only_admin_reporter_or_active_assignee(self):
        for user in (self.admin, self.owner):
            if user == self.owner:
                assignment = RescueAssignment.objects.create(
                    rescue_case=self.case, assignee=user, assigned_by=self.admin,
                )
            form = FundraisingCampaignForm(self.campaign_data(), user=user)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["rescue_case"], self.case)
        assignment.is_active = False
        assignment.save(update_fields=("is_active",))
        form = FundraisingCampaignForm(self.campaign_data(), user=self.owner)
        self.assertFalse(form.is_valid())
        self.case.reporter = self.owner
        self.case.save(update_fields=("reporter",))
        form = FundraisingCampaignForm(self.campaign_data(), user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)

    def test_campaign_create_prefill_cannot_bypass_unassigned_case_queryset(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("donations:campaign-create"), {"case": self.case.pk})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.case.title)
        self.assertNotContains(response, self.case.description)
        self.assertNotContains(response, self.case.contact_phone)
        self.assertNotIn("rescue_case", response.context["form"].initial)
