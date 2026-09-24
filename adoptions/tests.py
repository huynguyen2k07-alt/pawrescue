from datetime import timedelta
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from organizations.models import OrganizationMembership, RescueOrganization
from rescue.models import Notification, RescueCase

from .models import (
    AdoptionApplication,
    AdoptionFollowUp,
    AdoptionPlacement,
    AdoptionRestriction,
    AdoptionSafetyReport,
    AnimalProfile,
    AnimalProfileImage,
)


class AdoptionWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            email="adoption-manager@example.com",
            password="test-password",
            full_name="Adoption Manager",
        )
        self.applicant = user_model.objects.create_user(
            email="applicant@example.com",
            password="test-password",
            full_name="Loving Applicant",
            phone="0901111111",
        )
        self.second_applicant = user_model.objects.create_user(
            email="second-applicant@example.com",
            password="test-password",
            full_name="Second Applicant",
        )
        self.outsider = user_model.objects.create_user(
            email="outsider@example.com",
            password="test-password",
            full_name="Outside User",
        )
        self.admin = user_model.objects.create_superuser(
            email="admin@example.com",
            password="test-password",
            full_name="Site Admin",
        )
        self.organization = RescueOrganization.objects.create(
            name="Happy Tails Rescue",
            address="Ho Chi Minh City",
            created_by=self.manager,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=OrganizationMembership.Role.OWNER,
        )
        self.rescue_case = RescueCase.objects.create(
            title="Rescued cat ready for a home",
            description="Healthy after treatment.",
            animal_type=RescueCase.AnimalType.CAT,
            status=RescueCase.Status.RESCUED,
            reporter=self.applicant,
            organization=self.organization,
            address="District 3",
        )
        self.animal = AnimalProfile.objects.create(
            organization=self.organization,
            created_by=self.manager,
            name="Mướp",
            animal_type=AnimalProfile.AnimalType.CAT,
            breed="Mèo ta",
            sex=AnimalProfile.Sex.FEMALE,
            age_group=AnimalProfile.AgeGroup.YOUNG,
            size=AnimalProfile.Size.SMALL,
            description="Mướp hiền và thích được vuốt ve.",
            temperament="Thân thiện, hơi nhút nhát lúc mới gặp.",
            health_status="Khỏe mạnh.",
            vaccination_status=AnimalProfile.VaccinationStatus.COMPLETE,
            location="Quận 3, TP.HCM",
        )

    def application_data(self, name="Loving Applicant"):
        return {
            "applicant_name": name,
            "phone": "0901111111",
            "address": "District 7, Ho Chi Minh City",
            "housing_type": AdoptionApplication.HousingType.HOUSE,
            "other_pets": "Không có",
            "pet_experience": "Đã chăm sóc mèo trong 5 năm.",
            "reason": "Muốn mang đến một mái nhà lâu dài.",
            "agrees_no_resale": "on",
            "agrees_return_to_organization": "on",
            "agrees_follow_up": "on",
        }

    def create_application(self, user=None, **kwargs):
        user = user or self.applicant
        defaults = {
            "applicant_name": user.full_name,
            "phone": user.phone or "0902222222",
            "address": "Ho Chi Minh City",
            "housing_type": AdoptionApplication.HousingType.HOUSE,
            "reason": "Gia đình đã sẵn sàng nhận nuôi.",
            "agrees_no_resale": True,
            "agrees_return_to_organization": True,
            "agrees_follow_up": True,
            "pledge_accepted_at": timezone.now(),
        }
        defaults.update(kwargs)
        return AdoptionApplication.objects.create(
            animal=self.animal,
            applicant=user,
            **defaults,
        )

    def test_public_catalog_hides_adopted_animals(self):
        adopted = AnimalProfile.objects.create(
            organization=self.organization,
            name="Đã có nhà",
            animal_type=AnimalProfile.AnimalType.DOG,
            description="A rescued dog.",
            temperament="Calm.",
            health_status="Healthy.",
            location="District 1",
            status=AnimalProfile.Status.ADOPTED,
        )

        response = self.client.get(reverse("adoptions:animal-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mướp")
        self.assertNotContains(response, adopted.name)

    def test_catalog_filters_by_animal_type_and_age(self):
        AnimalProfile.objects.create(
            organization=self.organization,
            name="Bông",
            animal_type=AnimalProfile.AnimalType.DOG,
            age_group=AnimalProfile.AgeGroup.ADULT,
            description="Friendly dog.",
            temperament="Playful.",
            health_status="Healthy.",
            location="District 5",
        )

        response = self.client.get(
            reverse("adoptions:animal-list"),
            {
                "animal_type": AnimalProfile.AnimalType.CAT,
                "age_group": AnimalProfile.AgeGroup.YOUNG,
            },
        )

        self.assertContains(response, "Mướp")
        self.assertNotContains(response, "Bông")

    def test_manager_can_create_profile_with_image_from_rescue_case(self):
        self.client.force_login(self.manager)
        image = SimpleUploadedFile(
            "adoption-cat.jpg",
            b"small-test-image",
            content_type="image/jpeg",
        )
        data = {
            "organization": self.organization.pk,
            "rescue_case": self.rescue_case.pk,
            "name": "Cam",
            "animal_type": AnimalProfile.AnimalType.CAT,
            "sex": AnimalProfile.Sex.MALE,
            "age_group": AnimalProfile.AgeGroup.YOUNG,
            "size": AnimalProfile.Size.SMALL,
            "description": "Đã hồi phục và sẵn sàng nhận nuôi.",
            "temperament": "Quấn người.",
            "health_status": "Khỏe mạnh.",
            "vaccination_status": AnimalProfile.VaccinationStatus.PARTIAL,
            "location": "Quận 3",
            "status": AnimalProfile.Status.AVAILABLE,
            "images": image,
        }

        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            response = self.client.post(reverse("adoptions:animal-create"), data)
            created = AnimalProfile.objects.get(name="Cam")
            self.assertRedirects(
                response,
                reverse("adoptions:animal-detail", args=(created.pk,)),
            )
            self.assertEqual(created.rescue_case, self.rescue_case)
            self.assertEqual(AnimalProfileImage.objects.filter(animal=created).count(), 1)

    def test_non_manager_cannot_create_profile(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("adoptions:animal-create"))

        self.assertEqual(response.status_code, 403)

    def test_site_admin_can_open_profile_posting_area(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("adoptions:animal-create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Đăng hồ sơ nhận nuôi")

    def test_custom_admin_dashboard_shows_pending_adoption_work(self):
        self.create_application()
        self.client.force_login(self.admin)

        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trung tâm vận hành")
        self.assertContains(response, "Đơn nhận nuôi mới")
        self.assertContains(response, self.animal.name)
        self.assertContains(response, "pawrescue_admin.css")

    def test_application_requires_complete_safety_pledge(self):
        self.client.force_login(self.applicant)
        data = self.application_data()
        data.pop("agrees_no_resale")

        response = self.client.post(
            reverse("adoptions:application-create", args=(self.animal.pk,)),
            data,
        )

        self.assertRedirects(
            response,
            reverse("adoptions:animal-detail", args=(self.animal.pk,)),
        )
        self.assertFalse(
            AdoptionApplication.objects.filter(
                animal=self.animal,
                applicant=self.applicant,
            ).exists()
        )

    def test_applicant_can_submit_once_and_manager_is_notified(self):
        self.client.force_login(self.applicant)

        first_response = self.client.post(
            reverse("adoptions:application-create", args=(self.animal.pk,)),
            self.application_data(),
        )
        second_response = self.client.post(
            reverse("adoptions:application-create", args=(self.animal.pk,)),
            self.application_data(),
        )

        self.assertRedirects(first_response, reverse("adoptions:my-applications"))
        self.assertRedirects(second_response, reverse("adoptions:my-applications"))
        self.assertEqual(
            AdoptionApplication.objects.filter(
                animal=self.animal,
                applicant=self.applicant,
            ).count(),
            1,
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.manager,
                kind=Notification.Kind.ADOPTION_SUBMITTED,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin,
                kind=Notification.Kind.ADOPTION_SUBMITTED,
            ).exists()
        )
        application = AdoptionApplication.objects.get(
            animal=self.animal,
            applicant=self.applicant,
        )
        self.assertTrue(application.has_safety_pledge)

    def test_manager_approval_adopts_animal_and_closes_other_applications(self):
        approved = self.create_application(self.applicant)
        rejected = self.create_application(self.second_applicant)
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("adoptions:application-review", args=(approved.pk,)),
            {
                "status": AdoptionApplication.Status.APPROVED,
                "review_note": "Gia đình phù hợp và đã phỏng vấn.",
                "identity_confirmed": "on",
            },
        )

        self.assertRedirects(response, reverse("adoptions:dashboard"))
        self.animal.refresh_from_db()
        approved.refresh_from_db()
        rejected.refresh_from_db()
        self.assertEqual(self.animal.status, AnimalProfile.Status.ADOPTED)
        self.assertIsNotNone(self.animal.adopted_at)
        self.assertEqual(approved.status, AdoptionApplication.Status.APPROVED)
        self.assertEqual(rejected.status, AdoptionApplication.Status.REJECTED)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.applicant,
                kind=Notification.Kind.ADOPTION_REVIEWED,
            ).exists()
        )
        placement = AdoptionPlacement.objects.get(application=approved)
        self.assertEqual(placement.adopter, self.applicant)
        self.assertTrue(placement.is_active)
        self.assertEqual(
            placement.next_follow_up_on,
            timezone.localdate() + timedelta(days=14),
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.second_applicant,
                kind=Notification.Kind.ADOPTION_REVIEWED,
            ).exists()
        )

    def test_applicant_can_withdraw_pending_application(self):
        application = self.create_application()
        self.client.force_login(self.applicant)

        response = self.client.post(
            reverse("adoptions:application-withdraw", args=(application.pk,))
        )

        self.assertRedirects(response, reverse("adoptions:my-applications"))
        application.refresh_from_db()
        self.assertEqual(application.status, AdoptionApplication.Status.WITHDRAWN)

    def test_regular_user_cannot_open_organization_dashboard(self):
        self.client.force_login(self.applicant)

        response = self.client.get(reverse("adoptions:dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_rescued_case_offers_adoption_profile_handoff_to_manager(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("rescue:case-detail", args=(self.rescue_case.pk,))
        )

        self.assertContains(response, "Tạo hồ sơ nhận nuôi")
        self.assertContains(response, f"?case={self.rescue_case.pk}")

    def test_adoption_notification_opens_target_page(self):
        notification = Notification.objects.create(
            recipient=self.manager,
            kind=Notification.Kind.ADOPTION_SUBMITTED,
            title="Có đơn nhận nuôi mới",
            target_url=reverse("adoptions:dashboard"),
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("rescue:notification-open", args=(notification.pk,))
        )

        self.assertRedirects(response, reverse("adoptions:dashboard"))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_restricted_user_cannot_submit_a_new_application(self):
        AdoptionRestriction.objects.create(
            user=self.applicant,
            organization=self.organization,
            reason="Đã xác nhận vi phạm cam kết ở lần nhận nuôi trước.",
            created_by=self.manager,
        )
        self.client.force_login(self.applicant)

        response = self.client.post(
            reverse("adoptions:application-create", args=(self.animal.pk,)),
            self.application_data(),
        )

        self.assertRedirects(
            response,
            reverse("adoptions:animal-detail", args=(self.animal.pk,)),
        )
        self.assertFalse(
            AdoptionApplication.objects.filter(applicant=self.applicant).exists()
        )

    def test_user_can_report_suspected_sale_and_manager_is_notified(self):
        self.client.force_login(self.outsider)

        response = self.client.post(
            reverse("adoptions:safety-report-create", args=(self.animal.pk,)),
            {
                "reason": AdoptionSafetyReport.Reason.SALE_LISTING,
                "description": "Nhìn thấy bài đăng rao bán có ảnh và tên trùng khớp.",
                "evidence_url": "https://example.com/evidence",
            },
        )

        self.assertRedirects(
            response,
            reverse("adoptions:animal-detail", args=(self.animal.pk,)),
        )
        self.assertTrue(
            AdoptionSafetyReport.objects.filter(
                animal=self.animal,
                reporter=self.outsider,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.manager,
                kind=Notification.Kind.ADOPTION_SAFETY,
            ).exists()
        )

    def test_confirmed_safety_report_flags_placement_and_restricts_adopter(self):
        application = self.create_application()
        self.client.force_login(self.manager)
        self.client.post(
            reverse("adoptions:application-review", args=(application.pk,)),
            {
                "status": AdoptionApplication.Status.APPROVED,
                "review_note": "Đã phỏng vấn và xác minh.",
                "identity_confirmed": "on",
            },
        )
        placement = AdoptionPlacement.objects.get(application=application)
        report = AdoptionSafetyReport.objects.create(
            animal=self.animal,
            placement=placement,
            reporter=self.outsider,
            reason=AdoptionSafetyReport.Reason.SALE_LISTING,
            description="Phát hiện hồ sơ rao bán công khai.",
        )

        response = self.client.post(
            reverse("adoptions:safety-report-review", args=(report.pk,)),
            {
                "status": AdoptionSafetyReport.Status.CONFIRMED,
                "review_note": "Đã đối chiếu bài đăng và liên hệ người nhận nuôi.",
            },
        )

        self.assertRedirects(response, reverse("adoptions:dashboard"))
        placement.refresh_from_db()
        report.refresh_from_db()
        self.assertEqual(placement.status, AdoptionPlacement.Status.FLAGGED)
        self.assertEqual(report.status, AdoptionSafetyReport.Status.CONFIRMED)
        self.assertTrue(
            AdoptionRestriction.objects.filter(
                user=self.applicant,
                organization=self.organization,
                is_active=True,
            ).exists()
        )

    def test_follow_up_suspected_resale_creates_restriction(self):
        application = self.create_application()
        placement = AdoptionPlacement.objects.create(
            application=application,
            animal=self.animal,
            adopter=self.applicant,
            organization=self.organization,
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("adoptions:placement-follow-up", args=(placement.pk,)),
            {
                "contact_method": AdoptionFollowUp.ContactMethod.PHONE,
                "outcome": AdoptionFollowUp.Outcome.SUSPECTED_RESALE,
                "notes": "Người nhận nuôi xác nhận đã đăng tin bán.",
            },
        )

        self.assertRedirects(response, reverse("adoptions:dashboard"))
        placement.refresh_from_db()
        self.assertEqual(placement.status, AdoptionPlacement.Status.FLAGGED)
        self.assertTrue(
            AdoptionRestriction.objects.filter(
                user=self.applicant,
                organization=self.organization,
                is_active=True,
            ).exists()
        )
