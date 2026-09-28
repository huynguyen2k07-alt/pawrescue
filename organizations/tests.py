from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import OrganizationMembership, RescueOrganization


class OrganizationModelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="owner@example.com",
            password="test-password",
            full_name="Organization Owner",
        )
        self.member_user = user_model.objects.create_user(
            email="member@example.com",
            password="test-password",
            full_name="Organization Member",
        )
        self.organization = RescueOrganization.objects.create(
            name="Happy Paws Rescue",
            created_by=self.user,
        )

    def test_organization_string_representation(self):
        self.assertEqual(str(self.organization), "Happy Paws Rescue")

    def test_user_can_join_organization_with_a_role(self):
        membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )

        self.assertEqual(membership.get_role_display(), "Chủ tổ chức")
        self.assertIn(self.user, self.organization.members.all())

    def test_membership_is_unique_per_user_and_organization(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=self.user,
            )

    def test_member_can_open_organization_dashboard(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("organizations:dashboard"))

        self.assertContains(response, "Happy Paws Rescue")

    def test_user_can_create_organization_and_becomes_owner(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("organizations:organization-create"),
            {
                "name": "Second Chance Rescue",
                "description": "Community rescue team",
                "email": "team@example.com",
                "phone": "0901234567",
                "address": "Ho Chi Minh City",
            },
        )

        organization = RescueOrganization.objects.get(name="Second Chance Rescue")
        self.assertRedirects(
            response,
            reverse("organizations:organization-detail", args=(organization.pk,)),
        )
        self.assertTrue(
            OrganizationMembership.objects.filter(
                organization=organization,
                user=self.user,
                role=OrganizationMembership.Role.OWNER,
                is_active=True,
            ).exists()
        )

    def test_user_cannot_create_reserved_pawrescue_identity(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("organizations:organization-create"),
            {
                "name": "  pawRESCUE  ",
                "description": "Attempted takeover",
                "email": "fake@example.com",
                "phone": "0901234567",
                "address": "Da Nang",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tên PawRescue được dành riêng cho hệ thống.")
        self.assertFalse(
            RescueOrganization.objects.filter(
                name__iexact="pawrescue",
                is_system=False,
            ).exists()
        )

    def test_user_cannot_rename_organization_to_reserved_identity(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("organizations:organization-update", args=(self.organization.pk,)),
            {
                "name": "PawRescue",
                "description": "Attempted takeover",
                "email": "fake@example.com",
                "phone": "0901234567",
                "address": "Da Nang",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Happy Paws Rescue")

    def test_system_organization_cannot_have_user_membership(self):
        system_organization, _created = RescueOrganization.objects.get_or_create(
            is_system=True,
            defaults={
                "name": "PawRescue",
                "is_verified": True,
                "is_active": True,
            },
        )

        with self.assertRaises(ValidationError):
            OrganizationMembership.objects.create(
                organization=system_organization,
                user=self.user,
                role=OrganizationMembership.Role.OWNER,
            )

    def test_non_member_cannot_view_organization_management(self):
        self.client.force_login(self.member_user)

        response = self.client.get(
            reverse("organizations:organization-detail", args=(self.organization.pk,))
        )

        self.assertEqual(response.status_code, 403)

    def test_owner_can_update_organization(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("organizations:organization-update", args=(self.organization.pk,)),
            {
                "name": "Happy Paws Network",
                "description": "Updated profile",
                "email": "hello@example.com",
                "phone": "0901234567",
                "address": "District 3",
            },
        )

        self.assertRedirects(
            response,
            reverse("organizations:organization-detail", args=(self.organization.pk,)),
        )
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Happy Paws Network")

    def test_owner_can_add_existing_user_and_change_role(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )
        self.client.force_login(self.user)

        add_response = self.client.post(
            reverse("organizations:member-add", args=(self.organization.pk,)),
            {
                "email": "MEMBER@example.com",
                "role": OrganizationMembership.Role.VOLUNTEER,
            },
        )
        membership = OrganizationMembership.objects.get(
            organization=self.organization,
            user=self.member_user,
        )
        role_response = self.client.post(
            reverse(
                "organizations:member-change-role",
                args=(self.organization.pk, membership.pk),
            ),
            {"role": OrganizationMembership.Role.MANAGER},
        )

        self.assertEqual(add_response.status_code, 302)
        self.assertEqual(role_response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.MANAGER)

    def test_non_owner_cannot_add_member(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.MANAGER,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("organizations:member-add", args=(self.organization.pk,)),
            {
                "email": self.member_user.email,
                "role": OrganizationMembership.Role.VOLUNTEER,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            OrganizationMembership.objects.filter(
                organization=self.organization,
                user=self.member_user,
            ).exists()
        )

    def test_last_owner_cannot_be_demoted_or_removed(self):
        membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )
        self.client.force_login(self.user)

        self.client.post(
            reverse(
                "organizations:member-change-role",
                args=(self.organization.pk, membership.pk),
            ),
            {"role": OrganizationMembership.Role.MANAGER},
        )
        self.client.post(
            reverse(
                "organizations:member-remove",
                args=(self.organization.pk, membership.pk),
            )
        )

        membership.refresh_from_db()
        self.assertEqual(membership.role, OrganizationMembership.Role.OWNER)
        self.assertTrue(membership.is_active)

    def test_owner_can_remove_non_owner_member(self):
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
        )
        member = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.member_user,
            role=OrganizationMembership.Role.VOLUNTEER,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                "organizations:member-remove",
                args=(self.organization.pk, member.pk),
            )
        )

        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertFalse(member.is_active)
