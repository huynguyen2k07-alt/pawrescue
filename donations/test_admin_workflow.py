from decimal import Decimal
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from organizations.models import RescueOrganization
from rescue.models import Notification, RescueCase

from .models import CampaignExpense, Donation, FundraisingCampaign


PDF_DOCUMENT = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


class FundraisingAdminWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.admin = user_model.objects.create_superuser(
            email="fundraising-admin@example.com", password="test-password"
        )
        cls.donor = user_model.objects.create_user(
            email="fundraising-member@example.com", password="test-password",
            full_name="Secondary test donor",
        )
        cls.system = RescueOrganization.objects.get(is_system=True)
        cls.organization = RescueOrganization.objects.create(
            name="Admin fundraising test organization", is_verified=True
        )
        cls.campaign = FundraisingCampaign.objects.create(
            organization=cls.system, title="System emergency fund",
            description="Medication and rescue transport", target_amount=1000000,
            status=FundraisingCampaign.Status.ACTIVE,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def donation_data(self, **changes):
        data = {
            "campaign": self.campaign.pk, "donor": self.donor.pk,
            "donor_name": self.donor.full_name, "donor_email": self.donor.email,
            "amount": "1000000", "method": Donation.Method.BANK_TRANSFER,
            "status": Donation.Status.PENDING,
        }
        data.update(changes)
        return data

    def campaign_data(self, **changes):
        data = {
            "organization": self.system.pk, "title": self.campaign.title,
            "description": self.campaign.description, "target_amount": "1000000",
            "status": FundraisingCampaign.Status.ACTIVE,
            "donations-TOTAL_FORMS": "0", "donations-INITIAL_FORMS": "0",
            "donations-MIN_NUM_FORMS": "0", "donations-MAX_NUM_FORMS": "1000",
            "expenses-TOTAL_FORMS": "0", "expenses-INITIAL_FORMS": "0",
            "expenses-MIN_NUM_FORMS": "0", "expenses-MAX_NUM_FORMS": "1000",
        }
        data.update(changes)
        return data

    def create_donation(self, **changes):
        data = self.donation_data(**changes)
        data.pop("campaign")
        data.pop("donor")
        return Donation.objects.create(campaign=self.campaign, donor=self.donor, **data)

    def test_admin_can_open_all_fundraising_lists_and_add_forms(self):
        for model in ("fundraisingcampaign", "donation", "campaignexpense"):
            for action in ("changelist", "add"):
                with self.subTest(model=model, action=action):
                    response = self.client.get(reverse(f"admin:donations_{model}_{action}"))
                    self.assertEqual(response.status_code, 200)

    def test_regular_member_cannot_enter_any_fundraising_admin_page(self):
        self.client.force_login(self.donor)
        for model in ("fundraisingcampaign", "donation", "campaignexpense"):
            with self.subTest(model=model):
                response = self.client.get(reverse(f"admin:donations_{model}_changelist"))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response.url)

    def test_secondary_donor_submission_notifies_main_admin_for_system_campaign(self):
        self.client.force_login(self.donor)
        response = self.client.post(
            reverse("donations:donation-create", args=(self.campaign.pk,)),
            self.donation_data(status=Donation.Status.CONFIRMED, confirmed_by=self.donor.pk),
        )
        self.assertRedirects(response, reverse("donations:my-donations"))
        donation = Donation.objects.get()
        self.assertEqual(donation.donor, self.donor)
        self.assertEqual(donation.status, Donation.Status.PENDING)
        self.assertIsNone(donation.confirmed_by)
        self.assertTrue(Notification.objects.filter(
            recipient=self.admin, kind=Notification.Kind.DONATION_SUBMITTED
        ).exists())

    def test_admin_confirmation_stamps_reviewer_completes_campaign_and_notifies_donor(self):
        donation = self.create_donation()
        response = self.client.post(
            reverse("admin:donations_donation_change", args=(donation.pk,)),
            self.donation_data(status=Donation.Status.CONFIRMED, confirmed_by=self.donor.pk),
        )
        self.assertEqual(response.status_code, 302)
        donation.refresh_from_db()
        self.campaign.refresh_from_db()
        self.assertEqual(donation.confirmed_by, self.admin)
        self.assertIsNotNone(donation.confirmed_at)
        self.assertEqual(self.campaign.status, FundraisingCampaign.Status.COMPLETED)
        self.assertEqual(Notification.objects.filter(
            recipient=self.donor, kind=Notification.Kind.DONATION_REVIEWED
        ).count(), 1)

    def test_admin_inline_confirmation_uses_the_same_review_workflow(self):
        donation = self.create_donation()
        inline_data = {
            f"donations-0-{key}": value
            for key, value in self.donation_data(status=Donation.Status.CONFIRMED).items()
            if key != "campaign"
        }
        response = self.client.post(
            reverse("admin:donations_fundraisingcampaign_change", args=(self.campaign.pk,)),
            self.campaign_data(**inline_data, **{
                "donations-TOTAL_FORMS": "1", "donations-INITIAL_FORMS": "1",
                "donations-0-id": donation.pk,
            }),
        )
        self.assertEqual(response.status_code, 302)
        donation.refresh_from_db()
        self.campaign.refresh_from_db()
        self.assertEqual(donation.confirmed_by, self.admin)
        self.assertIsNotNone(donation.confirmed_at)
        self.assertEqual(self.campaign.status, FundraisingCampaign.Status.COMPLETED)
        self.assertTrue(Notification.objects.filter(
            recipient=self.donor, kind=Notification.Kind.DONATION_REVIEWED
        ).exists())

    def test_editing_reviewed_donation_does_not_send_duplicate_review_notification(self):
        donation = self.create_donation()
        url = reverse("admin:donations_donation_change", args=(donation.pk,))
        self.client.post(url, self.donation_data(status=Donation.Status.CONFIRMED))
        donation.refresh_from_db()
        first_review_time = donation.confirmed_at
        response = self.client.post(url, self.donation_data(
            status=Donation.Status.CONFIRMED, message="Internal correction"
        ))
        self.assertEqual(response.status_code, 302)
        donation.refresh_from_db()
        self.assertEqual(donation.confirmed_at, first_review_time)
        self.assertEqual(Notification.objects.filter(
            recipient=self.donor, kind=Notification.Kind.DONATION_REVIEWED
        ).count(), 1)

    def test_admin_can_reject_and_reset_donation_without_stale_confirmation(self):
        donation = self.create_donation()
        url = reverse("admin:donations_donation_change", args=(donation.pk,))
        for status in (Donation.Status.CONFIRMED, Donation.Status.REJECTED, Donation.Status.PENDING):
            response = self.client.post(url, self.donation_data(status=status))
            self.assertEqual(response.status_code, 302)
            donation.refresh_from_db()
            self.assertEqual(donation.status, status)
            if status != Donation.Status.CONFIRMED:
                self.assertIsNone(donation.confirmed_at)
            if status == Donation.Status.PENDING:
                self.assertIsNone(donation.confirmed_by)
            self.campaign.refresh_from_db()
            self.assertEqual(self.campaign.status, FundraisingCampaign.Status.COMPLETED)
            expected_amount = self.campaign.target_amount if status == Donation.Status.CONFIRMED else 0
            self.assertEqual(self.campaign.confirmed_amount, expected_amount)
            self.assertEqual(self.campaign.balance_amount, expected_amount)

    def test_admin_can_add_and_delete_donation(self):
        response = self.client.post(reverse("admin:donations_donation_add"), self.donation_data())
        self.assertEqual(response.status_code, 302)
        donation = Donation.objects.get()
        response = self.client.post(
            reverse("admin:donations_donation_delete", args=(donation.pk,)), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Donation.objects.exists())

    def test_admin_can_add_edit_and_delete_campaign(self):
        response = self.client.post(
            reverse("admin:donations_fundraisingcampaign_add"),
            self.campaign_data(title="New campaign"),
        )
        self.assertEqual(response.status_code, 302)
        campaign = FundraisingCampaign.objects.get(title="New campaign")
        self.assertEqual(campaign.created_by, self.admin)
        response = self.client.post(
            reverse("admin:donations_fundraisingcampaign_change", args=(campaign.pk,)),
            self.campaign_data(title="Corrected campaign"),
        )
        self.assertEqual(response.status_code, 302)
        campaign.refresh_from_db()
        self.assertEqual(campaign.title, "Corrected campaign")
        response = self.client.post(
            reverse("admin:donations_fundraisingcampaign_delete", args=(campaign.pk,)),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FundraisingCampaign.objects.filter(pk=campaign.pk).exists())

    def test_admin_can_add_edit_and_delete_expense(self):
        data = {
            "campaign": self.campaign.pk, "category": CampaignExpense.Category.MEDICAL,
            "amount": "50000", "description": "Initial examination", "spent_at": "2026-10-27",
        }
        response = self.client.post(reverse("admin:donations_campaignexpense_add"), data)
        self.assertEqual(response.status_code, 302)
        expense = CampaignExpense.objects.get()
        self.assertEqual(expense.recorded_by, self.admin)
        response = self.client.post(
            reverse("admin:donations_campaignexpense_change", args=(expense.pk,)),
            {**data, "amount": "70000"},
        )
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal("70000"))
        response = self.client.post(
            reverse("admin:donations_campaignexpense_delete", args=(expense.pk,)),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CampaignExpense.objects.exists())

    def test_admin_rejects_cross_organization_case_and_reversed_campaign_dates(self):
        other_case = RescueCase.objects.create(
            title="Other organization case", description="Restricted relation",
            address="District 3", reporter=self.donor, organization=self.organization,
        )
        response = self.client.post(
            reverse("admin:donations_fundraisingcampaign_add"),
            self.campaign_data(rescue_case=other_case.pk, starts_at="2026-10-27", ends_at="2026-10-26"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("rescue_case", response.context["adminform"].form.errors)
        self.assertIn("ends_at", response.context["adminform"].form.errors)
        self.assertEqual(FundraisingCampaign.objects.count(), 1)

    def test_invalid_admin_upload_is_a_form_error_instead_of_server_error(self):
        response = self.client.post(
            reverse("admin:donations_donation_add"),
            self.donation_data(proof=SimpleUploadedFile(
                "fake.pdf", b"not really a pdf", content_type="application/pdf"
            )),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("proof", response.context["adminform"].form.errors)
        self.assertFalse(Donation.objects.exists())

    def test_admin_can_open_existing_private_proof_and_receipt_editors(self):
        with TemporaryDirectory() as private_root, override_settings(PRIVATE_DONATION_MEDIA_ROOT=private_root):
            donation = self.create_donation(proof=SimpleUploadedFile(
                "proof.pdf", PDF_DOCUMENT, content_type="application/pdf"
            ))
            expense = CampaignExpense.objects.create(
                campaign=self.campaign, category=CampaignExpense.Category.MEDICAL,
                amount=10000, description="Private receipt", spent_at="2026-10-27",
                receipt=SimpleUploadedFile("receipt.pdf", PDF_DOCUMENT, content_type="application/pdf"),
            )
            for model, obj in (("donation", donation), ("campaignexpense", expense), ("fundraisingcampaign", self.campaign)):
                with self.subTest(model=model):
                    response = self.client.get(reverse(f"admin:donations_{model}_change", args=(obj.pk,)))
                    self.assertEqual(response.status_code, 200)
                    if model in ("donation", "fundraisingcampaign"):
                        self.assertContains(response, reverse("donations:donation-proof", args=(donation.pk,)))
                    if model in ("campaignexpense", "fundraisingcampaign"):
                        self.assertContains(response, reverse("donations:expense-receipt", args=(expense.pk,)))

    def test_admin_can_remove_private_proof_without_uploading_a_replacement(self):
        with TemporaryDirectory() as private_root, override_settings(PRIVATE_DONATION_MEDIA_ROOT=private_root):
            donation = self.create_donation(proof=SimpleUploadedFile(
                "proof.pdf", PDF_DOCUMENT, content_type="application/pdf"
            ))
            url = reverse("admin:donations_donation_change", args=(donation.pk,))
            editor = self.client.get(url)
            self.assertContains(editor, 'name="proof-clear"')
            response = self.client.post(url, self.donation_data(**{"proof-clear": "on"}))
            self.assertEqual(response.status_code, 302)
            donation.refresh_from_db()
            self.assertFalse(donation.proof)

    def test_closed_campaign_refuses_new_donations(self):
        self.campaign.status = FundraisingCampaign.Status.CLOSED
        self.campaign.save(update_fields=("status",))
        self.client.force_login(self.donor)
        response = self.client.post(
            reverse("donations:donation-create", args=(self.campaign.pk,)), self.donation_data()
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Donation.objects.exists())

    def test_delegated_financial_viewer_can_open_evidence_from_admin_links(self):
        viewer = get_user_model().objects.create_user(
            email="finance-viewer@example.com", password="test-password", is_staff=True
        )
        with TemporaryDirectory() as private_root, override_settings(PRIVATE_DONATION_MEDIA_ROOT=private_root):
            donation = self.create_donation(proof=SimpleUploadedFile(
                "proof.pdf", PDF_DOCUMENT, content_type="application/pdf"
            ))
            expense = CampaignExpense.objects.create(
                campaign=self.campaign, category=CampaignExpense.Category.MEDICAL,
                amount=10000, description="Private receipt", spent_at="2026-10-27",
                receipt=SimpleUploadedFile("receipt.pdf", PDF_DOCUMENT, content_type="application/pdf"),
            )
            self.client.force_login(viewer)
            for permission in ("view", "change"):
                viewer.user_permissions.set(Permission.objects.filter(
                    content_type__app_label="donations",
                    codename__in=(f"{permission}_donation", f"{permission}_campaignexpense"),
                ))
                for url in (
                    reverse("donations:donation-proof", args=(donation.pk,)),
                    reverse("donations:expense-receipt", args=(expense.pk,)),
                ):
                    with self.subTest(permission=permission, url=url):
                        response = self.client.get(url)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(b"".join(response.streaming_content), PDF_DOCUMENT)

    def test_repeat_public_review_is_idempotent(self):
        donation = self.create_donation()
        url = reverse("donations:donation-review", args=(donation.pk,))
        for _ in range(2):
            response = self.client.post(url, {"status": Donation.Status.CONFIRMED})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(
            recipient=self.donor, kind=Notification.Kind.DONATION_REVIEWED
        ).count(), 1)

    def test_live_database_finance_smoke_helper_rolls_back_all_qa_fixtures(self):
        from scripts.qa_finance_postgres import run_finance_checks

        models = (get_user_model(), FundraisingCampaign, Donation, CampaignExpense,
                  RescueOrganization, Notification)
        before = [model.objects.count() for model in models]
        report = run_finance_checks(self.admin, marker="QA-FINANCE-UNIT")
        self.assertTrue(report["rolled_back"])
        self.assertGreaterEqual(report["checks_passed"], 30)
        self.assertEqual([model.objects.count() for model in models], before)

    def test_review_of_a_concurrently_deleted_donation_does_not_recreate_it(self):
        from .services import save_reviewed_donation

        donation = self.create_donation()
        Donation.objects.filter(pk=donation.pk).delete()
        donation.status = Donation.Status.CONFIRMED
        result = save_reviewed_donation(donation, reviewer=self.admin, pending_only=True)
        self.assertIsNone(result)
        self.assertFalse(Donation.objects.exists())
