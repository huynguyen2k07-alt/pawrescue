"""Quản trị viên cứu hộ không được mở chứng từ riêng hoặc nhận điều phối quỹ."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import reverse

from organizations.models import OrganizationMembership, RescueOrganization

from .models import CampaignExpense, Donation, FundraisingCampaign
from .views import _manager_ids


@override_settings(SECURE_SSL_REDIRECT=False)
class ModeratorFinanceAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="finance-boundary-admin@example.com", password="test-password",
        )
        cls.moderator = users.objects.create_user(
            email="finance-boundary-moderator@example.com", password="test-password",
            role=users.Role.MODERATOR, is_staff=True,
        )
        cls.finance_staff = users.objects.create_user(
            email="finance-boundary-staff@example.com", password="test-password",
            is_staff=True,
        )
        cls.owner = users.objects.create_user(
            email="finance-boundary-owner@example.com", password="test-password",
        )
        cls.donor = users.objects.create_user(
            email="finance-boundary-donor@example.com", password="test-password",
        )
        cls.moderator.user_permissions.set(Permission.objects.filter(
            content_type__app_label="donations",
            codename__in=(
                "view_donation", "change_donation",
                "view_campaignexpense", "change_campaignexpense",
            ),
        ))
        cls.organization = RescueOrganization.objects.create(
            name="Tổ chức kiểm thử giới hạn quản trị viên cứu hộ", is_verified=True,
        )
        for user in (cls.moderator, cls.owner):
            OrganizationMembership.objects.create(
                organization=cls.organization, user=user,
                role=OrganizationMembership.Role.OWNER,
            )
        cls.campaign = FundraisingCampaign.objects.create(
            organization=cls.organization, title="Quỹ cứu hộ kiểm thử quyền chứng từ",
            description="Ghi nhận đóng góp và chi phí cứu hộ.", target_amount=1000000,
            status=FundraisingCampaign.Status.ACTIVE,
        )
        cls.donation = Donation.objects.create(
            campaign=cls.campaign, donor=cls.donor,
            donor_name="Người đóng góp", donor_email=cls.donor.email, amount=200000,
            proof="fixtures/private-donor-proof.pdf",
        )
        cls.expense = CampaignExpense.objects.create(
            campaign=cls.campaign, category=CampaignExpense.Category.MEDICAL,
            amount=100000, description="Chứng từ chi phí khám thú y riêng tư.",
            spent_at="2026-11-01", receipt="fixtures/private-expense-receipt.pdf",
            is_receipt_public=False,
        )

    def private_urls(self):
        return (
            reverse("donations:donation-proof", args=(self.donation.pk,)),
            reverse("donations:expense-receipt", args=(self.expense.pk,)),
        )

    def test_moderator_staff_permissions_and_ownership_cannot_open_other_peoples_private_files(self):
        self.client.force_login(self.moderator)
        self.assertTrue(self.moderator.has_perm("donations.view_donation"))
        self.assertTrue(self.moderator.has_perm("donations.change_campaignexpense"))
        self.assertTrue(self.organization.memberships.filter(
            user=self.moderator, role=OrganizationMembership.Role.OWNER,
        ).exists())
        for url in self.private_urls():
            with self.subTest(url=url), patch(
                "donations.views._private_file_response", return_value=HttpResponse("PRIVATE"),
            ) as serve_file:
                self.assertEqual(self.client.get(url).status_code, 404)
                serve_file.assert_not_called()

    def test_authorized_finance_staff_still_serves_private_files_with_view_or_change_permission(self):
        for permission in ("view", "change"):
            self.finance_staff.user_permissions.set(Permission.objects.filter(
                content_type__app_label="donations",
                codename__in=(f"{permission}_donation", f"{permission}_campaignexpense"),
            ))
            self.client.force_login(self.finance_staff)
            for url in self.private_urls():
                with self.subTest(permission=permission, url=url), patch(
                    "donations.views._private_file_response", return_value=HttpResponse("PRIVATE"),
                ) as serve_file:
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, b"PRIVATE")
                    serve_file.assert_called_once()

    def test_fund_manager_notifications_include_main_admin_and_owner_but_exclude_moderator_owner(self):
        self.assertEqual(_manager_ids(self.organization), {self.admin.pk, self.owner.pk})
