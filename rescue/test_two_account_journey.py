from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from adoptions.models import AdoptionApplication, AnimalProfile
from donations.models import Donation, FundraisingCampaign
from organizations.models import OrganizationMembership, RescueOrganization
from support.models import SupportConversation, SupportMessage

from .models import Notification, RescueAssignment, RescueCase, RescueUpdate


class AdminAndGuestJourneyTests(TestCase):
    """One connected journey using only an administrator and a guest account."""

    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            email="journey-admin@example.com",
            password="test-password",
            full_name="Journey Admin",
        )
        self.guest = user_model.objects.create_user(
            email="journey-guest@example.com",
            password="test-password",
            full_name="Journey Guest",
            phone="0901234567",
        )
        self.organization = RescueOrganization.objects.create(
            name="Journey Rescue Team",
            description="Organization used by the connected workflow test.",
            created_by=self.admin,
            is_verified=True,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=OrganizationMembership.Role.OWNER,
        )
        self.animal = AnimalProfile.objects.create(
            organization=self.organization,
            created_by=self.admin,
            name="Bông",
            animal_type=AnimalProfile.AnimalType.DOG,
            sex=AnimalProfile.Sex.FEMALE,
            age_group=AnimalProfile.AgeGroup.YOUNG,
            size=AnimalProfile.Size.MEDIUM,
            description="Đã hồi phục và đang tìm gia đình.",
            temperament="Thân thiện và năng động.",
            health_status="Khỏe mạnh.",
            location="TP.HCM",
            status=AnimalProfile.Status.AVAILABLE,
        )
        self.campaign = FundraisingCampaign.objects.create(
            organization=self.organization,
            created_by=self.admin,
            title="Quỹ kiểm thử hành trình cứu hộ",
            description="Chi phí điều trị và chăm sóc động vật.",
            target_amount=Decimal("1000000"),
            status=FundraisingCampaign.Status.ACTIVE,
        )

    def test_guest_submissions_and_admin_processing_work_end_to_end(self):
        self.client.force_login(self.guest)

        rescue_response = self.client.post(
            reverse("rescue:case-create"),
            {
                "title": "Chó bị thương cần hỗ trợ",
                "animal_type": RescueCase.AnimalType.DOG,
                "animal_details": "Lông vàng, đeo vòng cổ xanh",
                "urgency": RescueCase.Urgency.HIGH,
                "description": "Chó bị đau chân và đang nằm bên đường.",
                "address": "Hải Châu, Đà Nẵng",
                "latitude": "16.054407",
                "longitude": "108.202167",
                "contact_name": self.guest.full_name,
                "contact_phone": self.guest.phone,
            },
        )
        rescue_case = RescueCase.objects.get(reporter=self.guest)
        self.assertRedirects(
            rescue_response,
            reverse("rescue:case-detail", args=(rescue_case.pk,)),
        )

        adoption_response = self.client.post(
            reverse("adoptions:application-create", args=(self.animal.pk,)),
            {
                "applicant_name": self.guest.full_name,
                "phone": self.guest.phone,
                "address": "Quận 7, TP.HCM",
                "housing_type": AdoptionApplication.HousingType.HOUSE,
                "other_pets": "Không có",
                "pet_experience": "Đã chăm sóc chó trong ba năm.",
                "reason": "Muốn cho bé một mái nhà lâu dài.",
                "agrees_no_resale": "on",
                "agrees_return_to_organization": "on",
                "agrees_follow_up": "on",
            },
        )
        application = AdoptionApplication.objects.get(applicant=self.guest)
        self.assertRedirects(
            adoption_response,
            reverse("adoptions:my-applications"),
        )

        donation_response = self.client.post(
            reverse("donations:donation-create", args=(self.campaign.pk,)),
            {
                "donor_name": self.guest.full_name,
                "donor_email": self.guest.email,
                "amount": "250000",
                "method": Donation.Method.BANK_TRANSFER,
                "reference_code": "JOURNEY-001",
                "message": "Chúc các bé mau khỏe.",
            },
        )
        donation = Donation.objects.get(donor=self.guest)
        self.assertRedirects(
            donation_response,
            reverse("donations:my-donations"),
        )

        chat_response = self.client.post(
            reverse("support:chat-send"),
            {"body": "Tôi cần admin hỗ trợ kiểm tra các yêu cầu vừa gửi."},
        )
        self.assertEqual(chat_response.status_code, 201)
        conversation = SupportConversation.objects.get(user=self.guest)

        self.client.force_login(self.admin)
        admin_dashboard = self.client.get(reverse("admin:index"))
        self.assertContains(
            admin_dashboard,
            'data-model-count="rescue.rescuecase">1</strong>',
            html=False,
        )
        self.assertContains(
            admin_dashboard,
            'data-model-count="adoptions.adoptionapplication">1</strong>',
            html=False,
        )
        self.assertContains(
            admin_dashboard,
            'data-model-count="donations.donation">1</strong>',
            html=False,
        )
        self.assertContains(
            admin_dashboard,
            'data-model-count="support.supportconversation">1</strong>',
            html=False,
        )

        claim_response = self.client.post(
            reverse("rescue:case-claim", args=(rescue_case.pk,)),
            {"organization": self.organization.pk},
        )
        self.assertEqual(claim_response.status_code, 302)
        assign_response = self.client.post(
            reverse("rescue:case-assign", args=(rescue_case.pk,)),
            {"assignee": self.admin.pk, "notes": "Kiểm tra hiện trường."},
        )
        self.assertEqual(assign_response.status_code, 302)
        self.assertTrue(
            RescueAssignment.objects.filter(
                rescue_case=rescue_case,
                assignee=self.admin,
            ).exists()
        )
        status_response = self.client.post(
            reverse("rescue:case-update-status", args=(rescue_case.pk,)),
            {
                "status": RescueCase.Status.IN_PROGRESS,
                "note": "Đội cứu hộ đang trên đường đến.",
            },
        )
        self.assertEqual(status_response.status_code, 302)
        update_response = self.client.post(
            reverse("rescue:case-add-update", args=(rescue_case.pk,)),
            {"note": "Đã tiếp cận và sơ cứu cho động vật."},
        )
        self.assertEqual(update_response.status_code, 302)
        self.assertTrue(
            RescueUpdate.objects.filter(rescue_case=rescue_case).exists()
        )

        review_application_response = self.client.post(
            reverse("adoptions:application-review", args=(application.pk,)),
            {
                "status": AdoptionApplication.Status.APPROVED,
                "review_note": "Thông tin phù hợp.",
                "identity_confirmed": "on",
            },
        )
        self.assertRedirects(
            review_application_response,
            reverse("adoptions:dashboard"),
        )
        application.refresh_from_db()
        self.assertEqual(application.status, AdoptionApplication.Status.APPROVED)

        review_donation_response = self.client.post(
            reverse("donations:donation-review", args=(donation.pk,)),
            {"status": Donation.Status.CONFIRMED},
        )
        self.assertRedirects(
            review_donation_response,
            reverse("donations:dashboard"),
        )
        donation.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.CONFIRMED)

        reply_response = self.client.post(
            reverse("support:admin-reply", args=(conversation.pk,)),
            {"body": "Admin đã kiểm tra và xử lý các yêu cầu của bạn."},
        )
        self.assertEqual(reply_response.status_code, 302)

        self.client.force_login(self.guest)
        notification_response = self.client.get(reverse("rescue:notification-list"))
        self.assertContains(notification_response, "Ca cứu hộ đã được tiếp nhận")
        self.assertContains(notification_response, "Đơn nhận nuôi đã được cập nhật")
        self.assertContains(
            notification_response,
            "Đóng góp của bạn đã được cập nhật",
        )
        chat_state = self.client.get(reverse("support:chat-state")).json()
        self.assertTrue(
            any(
                item["is_admin"]
                and "đã kiểm tra" in item["body"]
                for item in chat_state["messages"]
            )
        )
        self.assertEqual(
            conversation.messages.filter(
                sender_role=SupportMessage.SenderRole.USER,
            ).count(),
            1,
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.guest,
                kind=Notification.Kind.STATUS_CHANGED,
            ).exists()
        )
