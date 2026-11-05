"""Tin báo chỉ được gửi sau khi người báo kiểm tra ghim và địa chỉ hiện trường."""

import base64
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import RescueCaseForm
from .models import Notification, RescueAssignment, RescueCase, RescueCaseImage


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@override_settings(SECURE_SSL_REDIRECT=False)
class LocationConfirmationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.reporter = users.objects.create_user(
            email="pin-reporter@example.com", password="test-password",
            full_name="Người báo tin",
        )
        cls.admin = users.objects.create_superuser(
            email="pin-admin@example.com", password="test-password",
        )
        cls.moderator = users.objects.create_user(
            email="pin-moderator@example.com", password="test-password",
            role=users.Role.MODERATOR,
        )
        cls.outsider = users.objects.create_user(
            email="pin-outsider@example.com", password="test-password",
        )

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings_override = override_settings(PRIVATE_RESCUE_MEDIA_ROOT=media.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.client.force_login(self.reporter)

    def payload(self, **changes):
        data = {
            "title": "Mèo bị thương trước cổng chợ",
            "animal_type": RescueCase.AnimalType.CAT,
            "urgency": RescueCase.Urgency.HIGH,
            "description": "Mèo bị thương ở chân, đang nằm trước cổng chợ.",
            "address": "Cổng chợ Hàn, 119 Trần Phú, Hải Châu, Đà Nẵng",
            "latitude": "16.067525", "longitude": "108.224049",
            "is_location_private": "on",
            "contact_phone": "0901234567",
            "location_confirmed": "on",
        }
        data.update(changes)
        return data

    def image(self):
        return SimpleUploadedFile("scene.png", PNG_1X1, content_type="image/png")

    def test_report_form_requires_explicit_confirmation_without_changing_legacy_form(self):
        response = self.client.get(reverse("rescue:case-create"))
        field = response.context["form"].fields["location_confirmed"]
        self.assertTrue(field.required)
        self.assertEqual(field.label, "Tôi đã kiểm tra ghim và địa chỉ đúng hiện trường")
        self.assertFalse(response.context["form"]["location_confirmed"].value())
        self.assertContains(response, 'id="id_location_confirmed"', count=1)

        legacy_data = self.payload()
        legacy_data.pop("location_confirmed")
        legacy_form = RescueCaseForm(data=legacy_data)
        self.assertFalse(legacy_form.fields["location_confirmed"].required)
        self.assertTrue(legacy_form.is_valid(), legacy_form.errors)

    def test_missing_or_false_confirmation_creates_no_case_image_or_notification(self):
        baseline = (
            RescueCase.objects.count(), RescueCaseImage.objects.count(),
            Notification.objects.count(),
        )
        for confirmation in (None, "", "false"):
            with self.subTest(confirmation=confirmation):
                data = self.payload(images=self.image())
                if confirmation is None:
                    data.pop("location_confirmed")
                else:
                    data["location_confirmed"] = confirmation
                response = self.client.post(reverse("rescue:case-create"), data)
                self.assertEqual(response.status_code, 200)
                self.assertIn("location_confirmed", response.context["form"].errors)
                self.assertIn(
                    "Hãy kiểm tra ghim và địa chỉ rồi xác nhận đúng hiện trường",
                    response.context["form"].errors["location_confirmed"][0],
                )
                self.assertEqual((
                    RescueCase.objects.count(), RescueCaseImage.objects.count(),
                    Notification.objects.count(),
                ), baseline)

    def test_confirmation_does_not_allow_missing_address_or_invalid_coordinates(self):
        for changes in (
            {"address": ""}, {"latitude": ""}, {"longitude": ""},
            {"latitude": "10.776900", "longitude": "106.700900"},
        ):
            with self.subTest(changes=changes):
                response = self.client.post(
                    reverse("rescue:case-create"), self.payload(**changes),
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertNotIn("location_confirmed", response.context["form"].errors)
                self.assertFalse(RescueCase.objects.exists())
                self.assertFalse(Notification.objects.exists())

    def test_confirmed_pin_reaches_assigned_moderator_with_exact_address_and_coordinates(self):
        response = self.client.post(
            reverse("rescue:case-create"), self.payload(images=self.image()),
        )
        case = RescueCase.objects.get(reporter=self.reporter)
        detail_url = reverse("rescue:case-detail", args=(case.pk,))
        self.assertRedirects(response, detail_url)
        self.assertEqual(case.address, self.payload()["address"])
        self.assertEqual(case.latitude, Decimal("16.067525"))
        self.assertEqual(case.longitude, Decimal("108.224049"))
        self.assertEqual(case.images.count(), 1)
        self.assertTrue(Notification.objects.filter(
            recipient=self.admin, rescue_case=case,
            kind=Notification.Kind.CASE_REPORTED,
        ).exists())
        self.assertFalse(Notification.objects.filter(recipient=self.moderator).exists())

        self.client.force_login(self.admin)
        assignment_response = self.client.post(
            reverse("rescue:case-assign", args=(case.pk,)),
            {"assignee": self.moderator.pk, "notes": "Đến đúng ghim người báo đã kiểm tra."},
        )
        self.assertRedirects(assignment_response, detail_url)
        self.assertTrue(RescueAssignment.objects.filter(
            rescue_case=case, assignee=self.moderator, is_active=True,
        ).exists())
        self.client.force_login(self.moderator)
        detail = self.client.get(detail_url)
        self.assertContains(detail, case.address)
        self.assertEqual(detail.context["map_latitude"], float(case.latitude))
        self.assertEqual(detail.context["map_longitude"], float(case.longitude))
        self.assertFalse(detail.context["map_is_approximate"])
        self.assertContains(detail, 'data-latitude="16.067525"')
        self.assertContains(detail, 'data-longitude="108.224049"')
        self.assertNotContains(detail, "data-accuracy")

        outsider = Client()
        outsider.force_login(self.outsider)
        self.assertEqual(outsider.get(detail_url).status_code, 404)
        case.change_status(
            RescueCase.Status.RESCUED, changed_by=self.admin,
            note="Admin đã kiểm tra kết quả cứu hộ và xác nhận hoàn tất.",
        )
        public_detail = Client().get(detail_url)
        self.assertEqual(public_detail.status_code, 200)
        self.assertTrue(public_detail.context["map_is_approximate"])
        self.assertNotContains(public_detail, case.address)
        self.assertNotContains(public_detail, 'data-latitude="16.067525"')
        self.assertNotContains(public_detail, 'data-longitude="108.224049"')
