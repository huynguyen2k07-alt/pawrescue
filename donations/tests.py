from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from organizations.models import OrganizationMembership, RescueOrganization
from rescue.models import Notification, RescueCase

from .forms import DonationForm
from .models import CampaignExpense, Donation, FundraisingCampaign


PDF_DOCUMENT = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


class FundraisingWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            email="fund-manager@example.com",
            password="test-password",
            full_name="Fund Manager",
        )
        self.donor = user_model.objects.create_user(
            email="donor@example.com",
            password="test-password",
            full_name="Kind Donor",
        )
        self.other_user = user_model.objects.create_user(
            email="other@example.com",
            password="test-password",
            full_name="Other User",
        )
        self.organization = RescueOrganization.objects.create(
            name="Transparent Rescue Fund",
            created_by=self.manager,
            address="Ho Chi Minh City",
            is_verified=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=OrganizationMembership.Role.OWNER,
        )
        self.rescue_case = RescueCase.objects.create(
            title="Emergency surgery for rescued dog",
            description="The dog needs urgent treatment.",
            animal_type=RescueCase.AnimalType.DOG,
            organization=self.organization,
            reporter=self.donor,
            address="District 5",
        )
        self.campaign = FundraisingCampaign.objects.create(
            organization=self.organization,
            rescue_case=self.rescue_case,
            created_by=self.manager,
            title="Help fund emergency surgery",
            description="Funds will cover surgery and medicine.",
            target_amount=Decimal("5000000"),
            bank_name="Test Bank",
            bank_account_name="TRANSPARENT RESCUE FUND",
            bank_account_number="123456789",
            transfer_content="SURGERY DOG",
            status=FundraisingCampaign.Status.ACTIVE,
        )

    def donation_data(self, amount="500000"):
        return {
            "donor_name": "Kind Donor",
            "donor_email": "donor@example.com",
            "amount": amount,
            "method": Donation.Method.BANK_TRANSFER,
            "reference_code": "TXN-001",
            "message": "Chúc bé mau khỏe.",
        }

    def test_public_campaign_list_hides_drafts_and_shows_confirmed_progress(self):
        FundraisingCampaign.objects.create(
            organization=self.organization,
            title="Private draft",
            description="Not public yet.",
            target_amount=Decimal("1000000"),
            status=FundraisingCampaign.Status.DRAFT,
        )
        Donation.objects.create(
            campaign=self.campaign,
            donor=self.donor,
            donor_name=self.donor.full_name,
            donor_email=self.donor.email,
            amount=Decimal("1000000"),
            status=Donation.Status.CONFIRMED,
        )
        Donation.objects.create(
            campaign=self.campaign,
            donor_name="Pending donor",
            donor_email="pending@example.com",
            amount=Decimal("2000000"),
        )

        response = self.client.get(reverse("donations:campaign-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.campaign.title)
        self.assertNotContains(response, "Private draft")
        listed_campaign = response.context["page_obj"].object_list[0]
        self.assertEqual(listed_campaign.confirmed_amount, Decimal("1000000"))
        self.assertEqual(listed_campaign.progress_percent, 20)

    def test_public_ledger_shows_confirmed_donations_and_expenses(self):
        Donation.objects.create(
            campaign=self.campaign,
            donor_name="Public Supporter",
            donor_email="public@example.com",
            amount=Decimal("800000"),
            status=Donation.Status.CONFIRMED,
        )
        Donation.objects.create(
            campaign=self.campaign,
            donor_name="Pending Supporter",
            donor_email="pending@example.com",
            amount=Decimal("900000"),
            status=Donation.Status.PENDING,
        )
        CampaignExpense.objects.create(
            campaign=self.campaign,
            category=CampaignExpense.Category.MEDICAL,
            amount=Decimal("300000"),
            description="Chi phí khám ban đầu",
            spent_at="2026-09-20",
            recorded_by=self.manager,
        )

        response = self.client.get(
            reverse("donations:campaign-detail", args=(self.campaign.pk,))
        )

        self.assertContains(response, "Public Supporter")
        self.assertNotContains(response, "Pending Supporter")
        self.assertContains(response, "Chi phí khám ban đầu")
        self.assertEqual(response.context["campaign"].balance_amount, Decimal("500000"))

    def test_manager_can_create_campaign_for_rescue_case(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("donations:campaign-create"),
            {
                "organization": self.organization.pk,
                "rescue_case": self.rescue_case.pk,
                "title": "Medication support",
                "description": "Funding medicine after surgery.",
                "target_amount": "2000000",
                "status": FundraisingCampaign.Status.ACTIVE,
            },
        )

        created = FundraisingCampaign.objects.get(title="Medication support")
        self.assertRedirects(
            response,
            reverse("donations:campaign-detail", args=(created.pk,)),
        )
        self.assertEqual(created.rescue_case, self.rescue_case)

    def test_non_manager_cannot_create_campaign_or_expense(self):
        self.client.force_login(self.other_user)

        create_response = self.client.get(reverse("donations:campaign-create"))
        expense_response = self.client.get(
            reverse("donations:expense-create", args=(self.campaign.pk,))
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(expense_response.status_code, 403)

    def test_donor_can_submit_contribution_and_manager_is_notified(self):
        self.client.force_login(self.donor)

        response = self.client.post(
            reverse("donations:donation-create", args=(self.campaign.pk,)),
            self.donation_data(),
        )

        self.assertRedirects(response, reverse("donations:my-donations"))
        donation = Donation.objects.get(donor=self.donor)
        self.assertEqual(donation.status, Donation.Status.PENDING)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.manager,
                kind=Notification.Kind.DONATION_SUBMITTED,
            ).exists()
        )

    def test_manager_confirmation_updates_campaign_and_notifies_donor(self):
        donation = Donation.objects.create(
            campaign=self.campaign,
            donor=self.donor,
            donor_name=self.donor.full_name,
            donor_email=self.donor.email,
            amount=self.campaign.target_amount,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("donations:donation-review", args=(donation.pk,)),
            {"status": Donation.Status.CONFIRMED},
        )

        self.assertRedirects(response, reverse("donations:dashboard"))
        donation.refresh_from_db()
        self.campaign.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.CONFIRMED)
        self.assertIsNotNone(donation.confirmed_at)
        self.assertEqual(self.campaign.status, FundraisingCampaign.Status.COMPLETED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.donor,
                kind=Notification.Kind.DONATION_REVIEWED,
            ).exists()
        )

    def test_outsider_cannot_confirm_donation(self):
        donation = Donation.objects.create(
            campaign=self.campaign,
            donor=self.donor,
            donor_name=self.donor.full_name,
            donor_email=self.donor.email,
            amount=Decimal("100000"),
        )
        self.client.force_login(self.other_user)

        response = self.client.post(
            reverse("donations:donation-review", args=(donation.pk,)),
            {"status": Donation.Status.CONFIRMED},
        )

        self.assertEqual(response.status_code, 403)
        donation.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.PENDING)

    def test_fake_pdf_proof_is_rejected_by_file_signature(self):
        form = DonationForm(
            data=self.donation_data(),
            files={
                "proof": SimpleUploadedFile(
                    "transfer-proof.pdf",
                    b"<script>alert('not a pdf')</script>",
                    content_type="application/pdf",
                )
            },
            user=self.donor,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("proof", form.errors)

    def test_manager_can_record_expense_with_private_receipt(self):
        self.client.force_login(self.manager)
        receipt = SimpleUploadedFile(
            "receipt.pdf",
            PDF_DOCUMENT,
            content_type="application/pdf",
        )
        with TemporaryDirectory() as private_root, override_settings(
            PRIVATE_DONATION_MEDIA_ROOT=private_root
        ):
            response = self.client.post(
                reverse("donations:expense-create", args=(self.campaign.pk,)),
                {
                    "category": CampaignExpense.Category.MEDICINE,
                    "amount": "450000",
                    "description": "Thuốc sau phẫu thuật",
                    "spent_at": "2026-09-20",
                    "receipt": receipt,
                },
            )
            self.assertRedirects(
                response,
                reverse("donations:campaign-detail", args=(self.campaign.pk,)),
            )
            expense = CampaignExpense.objects.get()
            self.assertFalse(expense.is_receipt_public)
            self.assertTrue(bool(expense.receipt))
            self.assertTrue((Path(private_root) / expense.receipt.name).is_file())

    def test_my_donations_only_shows_current_users_records(self):
        own = Donation.objects.create(
            campaign=self.campaign,
            donor=self.donor,
            donor_name=self.donor.full_name,
            donor_email=self.donor.email,
            amount=Decimal("100000"),
        )
        Donation.objects.create(
            campaign=self.campaign,
            donor=self.other_user,
            donor_name=self.other_user.full_name,
            donor_email=self.other_user.email,
            amount=Decimal("999999"),
        )
        self.client.force_login(self.donor)

        response = self.client.get(reverse("donations:my-donations"))

        self.assertContains(response, own.amount)
        self.assertNotContains(response, "999.999")

    def test_draft_campaign_is_private_except_for_manager(self):
        self.campaign.status = FundraisingCampaign.Status.DRAFT
        self.campaign.save(update_fields=("status",))
        detail_url = reverse("donations:campaign-detail", args=(self.campaign.pk,))

        anonymous_response = self.client.get(detail_url)
        self.client.force_login(self.manager)
        manager_response = self.client.get(detail_url)

        self.assertEqual(anonymous_response.status_code, 404)
        self.assertEqual(manager_response.status_code, 200)

    def test_unverified_organization_cannot_publish_or_manage_fundraising(self):
        unverified = RescueOrganization.objects.create(
            name="Unverified Fund",
            created_by=self.manager,
            is_verified=False,
        )
        OrganizationMembership.objects.create(
            organization=unverified,
            user=self.manager,
            role=OrganizationMembership.Role.OWNER,
        )
        hidden_campaign = FundraisingCampaign.objects.create(
            organization=unverified,
            created_by=self.manager,
            title="Unverified public campaign",
            description="This must not be public.",
            target_amount=Decimal("1000000"),
            status=FundraisingCampaign.Status.ACTIVE,
        )
        self.client.force_login(self.manager)

        create_response = self.client.get(reverse("donations:campaign-create"))
        update_response = self.client.get(
            reverse("donations:campaign-update", args=(hidden_campaign.pk,))
        )
        expense_response = self.client.get(
            reverse("donations:expense-create", args=(hidden_campaign.pk,))
        )
        detail_response = self.client.get(
            reverse("donations:campaign-detail", args=(hidden_campaign.pk,))
        )
        list_response = self.client.get(reverse("donations:campaign-list"))

        self.assertNotIn(
            unverified,
            create_response.context["form"].fields["organization"].queryset,
        )
        self.assertEqual(update_response.status_code, 403)
        self.assertEqual(expense_response.status_code, 403)
        self.assertEqual(detail_response.status_code, 404)
        self.assertNotContains(list_response, hidden_campaign.title)

    def test_donation_proof_is_private_and_only_authorized_users_can_open_it(self):
        with TemporaryDirectory() as private_root, override_settings(
            PRIVATE_DONATION_MEDIA_ROOT=private_root
        ):
            donation = Donation.objects.create(
                campaign=self.campaign,
                donor=self.donor,
                donor_name=self.donor.full_name,
                donor_email=self.donor.email,
                amount=Decimal("250000"),
                proof=SimpleUploadedFile(
                    "transfer-proof.pdf",
                    PDF_DOCUMENT,
                    content_type="application/pdf",
                ),
            )
            proof_url = reverse("donations:donation-proof", args=(donation.pk,))

            self.assertTrue((Path(private_root) / donation.proof.name).is_file())
            with self.assertRaises(ValueError):
                _ = donation.proof.url

            anonymous_response = self.client.get(proof_url)
            self.client.force_login(self.other_user)
            outsider_response = self.client.get(proof_url)
            self.client.force_login(self.donor)
            donor_response = self.client.get(proof_url)
            self.assertEqual(b"".join(donor_response.streaming_content), PDF_DOCUMENT)
            self.client.force_login(self.manager)
            manager_response = self.client.get(proof_url)
            self.assertEqual(b"".join(manager_response.streaming_content), PDF_DOCUMENT)

            self.assertEqual(anonymous_response.status_code, 404)
            self.assertEqual(outsider_response.status_code, 404)
            self.assertEqual(donor_response.status_code, 200)
            self.assertEqual(manager_response.status_code, 200)
            self.assertEqual(donor_response.headers["Cache-Control"], "private, no-store")
            self.assertEqual(
                donor_response.headers["X-Content-Type-Options"],
                "nosniff",
            )

    def test_public_and_private_receipt_access(self):
        with TemporaryDirectory() as private_root, override_settings(
            PRIVATE_DONATION_MEDIA_ROOT=private_root
        ):
            public_expense = CampaignExpense.objects.create(
                campaign=self.campaign,
                category=CampaignExpense.Category.MEDICAL,
                amount=Decimal("300000"),
                description="Public hospital receipt",
                spent_at="2026-09-21",
                receipt=SimpleUploadedFile(
                    "public-receipt.pdf",
                    PDF_DOCUMENT,
                    content_type="application/pdf",
                ),
                is_receipt_public=True,
                recorded_by=self.manager,
            )
            private_expense = CampaignExpense.objects.create(
                campaign=self.campaign,
                category=CampaignExpense.Category.MEDICINE,
                amount=Decimal("200000"),
                description="Private pharmacy receipt",
                spent_at="2026-09-22",
                receipt=SimpleUploadedFile(
                    "private-receipt.pdf",
                    PDF_DOCUMENT,
                    content_type="application/pdf",
                ),
                is_receipt_public=False,
                recorded_by=self.manager,
            )
            public_url = reverse(
                "donations:expense-receipt",
                args=(public_expense.pk,),
            )
            private_url = reverse(
                "donations:expense-receipt",
                args=(private_expense.pk,),
            )

            public_response = self.client.get(public_url)
            self.assertEqual(b"".join(public_response.streaming_content), PDF_DOCUMENT)
            anonymous_private_response = self.client.get(private_url)
            self.client.force_login(self.other_user)
            outsider_private_response = self.client.get(private_url)
            self.client.force_login(self.manager)
            manager_private_response = self.client.get(private_url)
            self.assertEqual(
                b"".join(manager_private_response.streaming_content),
                PDF_DOCUMENT,
            )

            self.assertEqual(public_response.status_code, 200)
            self.assertEqual(anonymous_private_response.status_code, 404)
            self.assertEqual(outsider_private_response.status_code, 404)
            self.assertEqual(manager_private_response.status_code, 200)
