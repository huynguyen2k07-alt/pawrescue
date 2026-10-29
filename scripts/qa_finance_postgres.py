"""Kiểm thử luồng tài chính và quản trị trên cơ sở dữ liệu đang cấu hình.

Mọi thay đổi, kể cả phiên đăng nhập tạm, thông báo và thời điểm đăng nhập cuối,
đều được hoàn tác. Chứng từ giả được lưu trong thư mục tạm rồi tự xóa.
Chỉ chạy trên cơ sở dữ liệu phát triển cục bộ và phải chọn rõ tài khoản quản trị.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4


def run_finance_checks(admin, marker):
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import transaction
    from django.test import Client, override_settings
    from django.urls import reverse
    from django.utils import timezone

    from donations.models import CampaignExpense, Donation, FundraisingCampaign
    from organizations.models import OrganizationMembership, RescueOrganization
    from rescue.models import Notification

    if not (admin.is_active and admin.is_staff and admin.is_superuser):
        raise ValueError("The selected account must be an active main administrator.")
    if not marker or len(marker) > 60:
        raise ValueError("Use a non-empty, unique QA marker of at most 60 characters.")

    checks = []

    def check(condition, description):
        if not condition:
            raise AssertionError(description)
        checks.append(description)

    def check_response(response, status, description):
        if response.status_code != status:
            details = ""
            if response.context and "adminform" in response.context:
                details = str(response.context["adminform"].form.errors)
            raise AssertionError(f"{description}: HTTP {response.status_code}, expected {status}. {details}")
        checks.append(description)

    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
    with TemporaryDirectory(prefix="pawrescue-finance-qa-") as media_root:
        root = Path(media_root)
        with override_settings(
            ALLOWED_HOSTS=list(set(settings.ALLOWED_HOSTS) | {"testserver"}),
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
            MEDIA_ROOT=root / "public",
            PRIVATE_DONATION_MEDIA_ROOT=root / "donations",
        ), transaction.atomic():
            try:
                admin_client, user_client = Client(), Client()
                admin_client.force_login(admin)
                user = get_user_model().objects.create_user(
                    email=f"{uuid4().hex}@finance-qa.invalid", password=secrets.token_urlsafe(24),
                    full_name=f"{marker} secondary donor",
                )
                user_client.force_login(user)
                for model in ("fundraisingcampaign", "donation", "campaignexpense"):
                    for action in ("changelist", "add"):
                        check_response(admin_client.get(reverse(f"admin:donations_{model}_{action}")), 200,
                                       f"Admin opens {model} {action}")

                system = RescueOrganization.objects.get(is_system=True)
                organization_data = {
                    "name": f"{marker} organization", "is_active": "on", "is_verified": "on",
                    "memberships-TOTAL_FORMS": "0", "memberships-INITIAL_FORMS": "0",
                    "memberships-MIN_NUM_FORMS": "0", "memberships-MAX_NUM_FORMS": "1000",
                }
                check_response(admin_client.post(reverse("admin:organizations_rescueorganization_add"),
                                                 organization_data), 302, "Admin creates verified QA organization")
                organization = RescueOrganization.objects.get(name=organization_data["name"])
                organization_data["address"] = f"{marker} corrected address"
                check_response(admin_client.post(reverse("admin:organizations_rescueorganization_change", args=(organization.pk,)),
                                                 organization_data), 302, "Admin updates QA organization")
                member_data = {"organization": organization.pk, "user": user.pk,
                               "role": OrganizationMembership.Role.VOLUNTEER, "is_active": "on"}
                check_response(admin_client.post(reverse("admin:organizations_organizationmembership_add"), member_data),
                               302, "Admin adds QA organization member")
                member = OrganizationMembership.objects.get(organization=organization, user=user)
                member_data["role"] = OrganizationMembership.Role.MANAGER
                check_response(admin_client.post(reverse("admin:organizations_organizationmembership_change", args=(member.pk,)), member_data),
                               302, "Admin changes QA membership role")

                campaign_data = {
                    "organization": system.pk, "title": f"{marker} rescue fund",
                    "description": f"{marker} finance regression", "target_amount": "1000000",
                    "status": FundraisingCampaign.Status.ACTIVE,
                    "donations-TOTAL_FORMS": "0", "donations-INITIAL_FORMS": "0",
                    "donations-MIN_NUM_FORMS": "0", "donations-MAX_NUM_FORMS": "1000",
                    "expenses-TOTAL_FORMS": "0", "expenses-INITIAL_FORMS": "0",
                    "expenses-MIN_NUM_FORMS": "0", "expenses-MAX_NUM_FORMS": "1000",
                }
                check_response(admin_client.post(reverse("admin:donations_fundraisingcampaign_add"), campaign_data),
                               302, "Admin creates campaign for system organization")
                campaign = FundraisingCampaign.objects.get(title=campaign_data["title"])
                donor_data = {"donor_name": user.full_name, "donor_email": user.email,
                              "amount": "600000", "method": Donation.Method.BANK_TRANSFER,
                              "reference_code": f"{marker}-first"}
                check_response(user_client.post(reverse("donations:donation-create", args=(campaign.pk,)), {
                    **donor_data, "status": Donation.Status.CONFIRMED,
                    "proof": SimpleUploadedFile("proof.pdf", pdf, content_type="application/pdf"),
                }), 302, "Secondary donor submits private evidence")
                first = Donation.objects.get(campaign=campaign, donor=user)
                check(first.status == Donation.Status.PENDING, "Donor cannot self-confirm through forged POST")
                check(Notification.objects.filter(recipient=admin, kind=Notification.Kind.DONATION_SUBMITTED,
                                                  message__contains=campaign.title).exists(),
                      "Main admin receives system-campaign submission notification")
                proof_response = admin_client.get(reverse("donations:donation-proof", args=(first.pk,)))
                check_response(proof_response, 200, "Main admin opens private donor proof")
                check(b"".join(proof_response.streaming_content) == pdf, "Private donor proof bytes are intact")
                review_url = reverse("donations:donation-review", args=(first.pk,))
                for attempt in range(2):
                    check_response(admin_client.post(review_url, {"status": Donation.Status.CONFIRMED}),
                                   302, f"PostgreSQL public review attempt {attempt + 1}")
                first.refresh_from_db()
                check(first.confirmed_by_id == admin.pk and first.confirmed_at is not None,
                      "Review stores actual reviewer and timestamp")
                check(Notification.objects.filter(recipient=user, kind=Notification.Kind.DONATION_REVIEWED,
                                                  message__contains=campaign.title).count() == 1,
                      "Repeat public review is idempotent")

                inline_data = dict(campaign_data)
                inline_data.update({"donations-TOTAL_FORMS": "2", "donations-INITIAL_FORMS": "1"})
                for index, amount in ((0, "600000"), (1, "400000")):
                    row = {**donor_data, "donor": user.pk, "amount": amount,
                           "status": Donation.Status.CONFIRMED, "reference_code": f"{marker}-{index}"}
                    inline_data.update({f"donations-{index}-{key}": value for key, value in row.items()})
                inline_data["donations-0-id"] = first.pk
                check_response(admin_client.post(reverse("admin:donations_fundraisingcampaign_change", args=(campaign.pk,)), inline_data),
                               302, "Admin inline confirmation shares the review workflow")
                second = campaign.donations.exclude(pk=first.pk).get()
                campaign.refresh_from_db()
                check(second.confirmed_by_id == admin.pk and second.confirmed_at is not None,
                      "Inline review stores actual reviewer and timestamp")
                check(campaign.status == FundraisingCampaign.Status.COMPLETED and campaign.confirmed_amount == 1000000,
                      "Confirmed funding reaches target and finalizes campaign")
                check_response(admin_client.post(reverse("admin:donations_donation_change", args=(second.pk,)), {
                    **donor_data, "campaign": campaign.pk, "donor": user.pk,
                    "amount": "400000", "status": Donation.Status.REJECTED,
                }), 302, "Admin can correct a previously confirmed donation")
                campaign.refresh_from_db()
                second.refresh_from_db()
                check(second.confirmed_at is None and campaign.confirmed_amount == 600000,
                      "Rejecting a donation clears confirmation and recomputes live funding")
                check(campaign.status == FundraisingCampaign.Status.COMPLETED,
                      "Financial corrections preserve campaign finalization")

                expense_data = {
                    "campaign": campaign.pk, "category": CampaignExpense.Category.MEDICAL,
                    "amount": "100000", "description": f"{marker} treatment",
                    "spent_at": timezone.localdate().isoformat(),
                }
                check_response(admin_client.post(reverse("admin:donations_campaignexpense_add"), {
                    **expense_data, "receipt": SimpleUploadedFile("receipt.pdf", pdf, content_type="application/pdf"),
                }), 302, "Admin records expense with private receipt")
                expense = CampaignExpense.objects.get(campaign=campaign)
                receipt_response = admin_client.get(reverse("donations:expense-receipt", args=(expense.pk,)))
                check_response(receipt_response, 200, "Main admin opens private expense receipt")
                check(b"".join(receipt_response.streaming_content) == pdf, "Private expense receipt bytes are intact")
                expense_data["amount"] = "150000"
                check_response(admin_client.post(reverse("admin:donations_campaignexpense_change", args=(expense.pk,)), expense_data),
                               302, "Admin updates expense without re-uploading evidence")
                check(campaign.balance_amount == 450000, "Live balance follows the updated expense")
                check_response(admin_client.post(reverse("admin:donations_donation_delete", args=(first.pk,)), {"post": "yes"}),
                               302, "Admin deletes QA confirmed donation")
                check(campaign.confirmed_amount == 0 and campaign.balance_amount == -150000,
                      "Deleting confirmed donation recomputes funding and balance")
                check_response(admin_client.post(reverse("admin:donations_campaignexpense_delete", args=(expense.pk,)), {"post": "yes"}),
                               302, "Admin deletes QA expense")
                check(campaign.balance_amount == 0, "Deleting expense recomputes balance")
                check_response(admin_client.post(reverse("admin:donations_fundraisingcampaign_delete", args=(campaign.pk,)), {"post": "yes"}),
                               302, "Admin deletes QA campaign")
                check_response(admin_client.post(reverse("admin:organizations_organizationmembership_delete", args=(member.pk,)), {"post": "yes"}),
                               302, "Admin deletes QA membership")
                check_response(admin_client.post(reverse("admin:organizations_rescueorganization_delete", args=(organization.pk,)), {"post": "yes"}),
                               302, "Admin deletes QA organization")
            finally:
                transaction.set_rollback(True)
    return {"marker": marker, "database": settings.DATABASES["default"]["ENGINE"],
            "rolled_back": True, "checks_passed": len(checks), "checks": checks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--marker", default=f"QA-FINANCE-{uuid4().hex[:10]}")
    arguments = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.contrib.auth import get_user_model

    selected_admin = get_user_model().objects.get(email=arguments.admin_email)
    print(json.dumps(run_finance_checks(selected_admin, arguments.marker), ensure_ascii=False, indent=2))
