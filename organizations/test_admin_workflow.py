from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rescue.models import RescueCase

from .models import OrganizationMembership, RescueOrganization


class OrganizationAdminWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            email="organization-audit-admin@example.com", password="test-password"
        )
        cls.member = get_user_model().objects.create_user(
            email="organization-audit-member@example.com", password="test-password"
        )
        cls.system = RescueOrganization.objects.get(is_system=True)
        cls.organization = RescueOrganization.objects.create(name="Ordinary test organization")

    def setUp(self):
        self.client.force_login(self.admin)

    def organization_data(self, **changes):
        data = {
            "name": self.organization.name, "is_active": "on",
            "memberships-TOTAL_FORMS": "0", "memberships-INITIAL_FORMS": "0",
            "memberships-MIN_NUM_FORMS": "0", "memberships-MAX_NUM_FORMS": "1000",
        }
        data.update(changes)
        return data

    def test_admin_can_open_both_organization_models(self):
        for model in ("rescueorganization", "organizationmembership"):
            for action in ("changelist", "add"):
                with self.subTest(model=model, action=action):
                    response = self.client.get(reverse(f"admin:organizations_{model}_{action}"))
                    self.assertEqual(response.status_code, 200)

    def test_admin_can_create_verify_edit_and_delete_ordinary_organization(self):
        response = self.client.post(
            reverse("admin:organizations_rescueorganization_add"),
            self.organization_data(name="New verified organization", is_verified="on"),
        )
        self.assertEqual(response.status_code, 302)
        organization = RescueOrganization.objects.get(name="New verified organization")
        self.assertTrue(organization.is_verified)
        response = self.client.post(
            reverse("admin:organizations_rescueorganization_change", args=(organization.pk,)),
            self.organization_data(name="Corrected organization", address="District 5"),
        )
        self.assertEqual(response.status_code, 302)
        organization.refresh_from_db()
        self.assertEqual(organization.name, "Corrected organization")
        self.assertEqual(organization.address, "District 5")
        response = self.client.post(
            reverse("admin:organizations_rescueorganization_delete", args=(organization.pk,)),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RescueOrganization.objects.filter(pk=organization.pk).exists())

    def test_system_identity_readonly_post_tampering_keeps_organization_operational(self):
        response = self.client.post(
            reverse("admin:organizations_rescueorganization_change", args=(self.system.pk,)),
            {"name": "Stolen identity", "created_by": self.member.pk, "email": "system@example.com",
             "is_verified": "", "is_active": "", "is_system": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.system.refresh_from_db()
        self.assertEqual(self.system.name, "PawRescue")
        self.assertEqual(self.system.email, "system@example.com")
        self.assertTrue(self.system.is_system)
        self.assertTrue(self.system.is_active)
        self.assertTrue(self.system.is_verified)
        self.assertIsNone(self.system.created_by)

    def test_system_admin_editor_does_not_offer_membership_or_delete(self):
        response = self.client.get(reverse(
            "admin:organizations_rescueorganization_change", args=(self.system.pk,)
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["inline_admin_formsets"], [])
        self.assertFalse(response.context["has_delete_permission"])

    def test_system_organization_cannot_be_deleted_individually_or_in_bulk(self):
        individual = self.client.post(
            reverse("admin:organizations_rescueorganization_delete", args=(self.system.pk,)),
            {"post": "yes"},
        )
        self.assertEqual(individual.status_code, 403)
        bulk = self.client.post(reverse("admin:organizations_rescueorganization_changelist"), {
            "action": "delete_selected", "_selected_action": [self.system.pk, self.organization.pk],
            "post": "yes",
        })
        self.assertEqual(bulk.status_code, 200)
        self.assertTrue(RescueOrganization.objects.filter(pk=self.system.pk).exists())
        self.assertTrue(RescueOrganization.objects.filter(pk=self.organization.pk).exists())

    def test_admin_cannot_create_reserved_identity_or_system_membership(self):
        reserved = self.client.post(
            reverse("admin:organizations_rescueorganization_add"),
            self.organization_data(name=" pawRESCUE "),
        )
        self.assertEqual(reserved.status_code, 200)
        self.assertIn("name", reserved.context["adminform"].form.errors)
        membership = self.client.post(reverse("admin:organizations_organizationmembership_add"), {
            "organization": self.system.pk, "user": self.member.pk,
            "role": OrganizationMembership.Role.OWNER, "is_active": "on",
        })
        self.assertEqual(membership.status_code, 200)
        self.assertIn("organization", membership.context["adminform"].form.errors)
        self.assertFalse(OrganizationMembership.objects.filter(organization=self.system).exists())

    def test_admin_can_create_edit_and_delete_ordinary_membership(self):
        data = {
            "organization": self.organization.pk, "user": self.member.pk,
            "role": OrganizationMembership.Role.VOLUNTEER, "is_active": "on",
        }
        response = self.client.post(reverse("admin:organizations_organizationmembership_add"), data)
        self.assertEqual(response.status_code, 302)
        membership = OrganizationMembership.objects.get()
        response = self.client.post(
            reverse("admin:organizations_organizationmembership_change", args=(membership.pk,)),
            {**data, "role": OrganizationMembership.Role.MANAGER},
        )
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.MANAGER)
        response = self.client.post(
            reverse("admin:organizations_organizationmembership_delete", args=(membership.pk,)),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(OrganizationMembership.objects.exists())

    def test_system_public_pages_send_admin_to_safe_editor_and_reject_ownership(self):
        update = self.client.get(reverse("organizations:organization-update", args=(self.system.pk,)))
        self.assertRedirects(update, reverse(
            "admin:organizations_rescueorganization_change", args=(self.system.pk,)
        ))
        add_member = self.client.post(reverse("organizations:member-add", args=(self.system.pk,)), {
            "email": self.member.email, "role": OrganizationMembership.Role.MANAGER,
        })
        self.assertEqual(add_member.status_code, 403)
        detail = self.client.get(reverse("organizations:organization-detail", args=(self.system.pk,)))
        self.assertFalse(detail.context["can_manage_members"])

    def test_regular_member_cannot_enter_admin_or_gain_organization_verification(self):
        self.client.force_login(self.member)
        admin = self.client.get(reverse("admin:organizations_rescueorganization_changelist"))
        self.assertEqual(admin.status_code, 302)
        response = self.client.post(reverse("organizations:organization-create"), {
            "name": "User submitted organization", "is_verified": "on", "is_system": "on",
        })
        self.assertEqual(response.status_code, 302)
        organization = RescueOrganization.objects.get(name="User submitted organization")
        self.assertFalse(organization.is_verified)
        self.assertFalse(organization.is_system)

    def test_org_dashboards_hide_unverified_reports_from_unassigned_members(self):
        OrganizationMembership.objects.create(
            organization=self.organization, user=self.member, role=OrganizationMembership.Role.MANAGER
        )
        private_case = RescueCase.objects.create(
            title="Private unverified report", description="Reporter details", address="District 1",
            organization=self.organization, reporter=self.admin,
        )
        self.client.force_login(self.member)
        for url in (
            reverse("organizations:dashboard"),
            reverse("organizations:organization-detail", args=(self.organization.pk,)),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(private_case, response.context["cases"])
                self.assertNotContains(response, private_case.title)
                if "organizations" in response.context:
                    self.assertEqual(response.context["organizations"][0].active_case_count, 0)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("organizations:dashboard"))
        self.assertIn(private_case, response.context["cases"])
