"""Kiểm tra dữ liệu vị trí xuyên suốt hành trình người dùng thường bằng Geoapify giả."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from .models import Notification, RescueAssignment, RescueCase, RescueCaseImage


@override_settings(
    SECURE_SSL_REDIRECT=False,
    GEOAPIFY_API_KEY="guest-journey-test-only-key",
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "guest-location-journey-tests",
    }},
)
class GuestLocationJourneyTests(TestCase):
    password = "Guest-location-test-password-2026"
    point = {
        "label": "Cổng chợ Hàn, 119 Trần Phú, Hải Châu, Đà Nẵng",
        "latitude": 16.067525,
        "longitude": 108.224049,
    }

    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="guest-journey-admin@example.invalid", password=cls.password,
            full_name="Admin kiểm thử",
        )
        cls.moderator = users.objects.create_user(
            email="guest-journey-moderator@example.invalid", password=cls.password,
            full_name="Người được giao ca", role=users.Role.MODERATOR,
        )

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.provider = self.enterContext(patch(
            "rescue.geocoding._search_provider", return_value=[dict(self.point)],
        ))
        self.enterContext(patch(
            "rescue.geocoding.build_opener",
            side_effect=AssertionError("Kiểm thử hành trình không được gọi mạng."),
        ))
        self.guest = Client(enforce_csrf_checks=True)
        self.member = self.register_and_log_in_guest()

    def post_with_csrf(self, client, url, data=None):
        return client.post(
            url, data or {}, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )

    def assert_regular_member(self):
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, self.member.Role.MEMBER)
        self.assertFalse(self.member.is_staff)
        self.assertFalse(self.member.is_superuser)
        self.assertTrue(self.member.is_active)

    def register_and_log_in_guest(self):
        register_url = reverse("accounts:register")
        self.assertEqual(self.guest.get(register_url).status_code, 200)
        registered = self.post_with_csrf(self.guest, register_url, {
            "email": "guest-location-journey@example.invalid",
            "full_name": "Người dùng thường kiểm thử",
            "phone": "0901234567",
            "password1": self.password,
            "password2": self.password,
        })
        self.assertRedirects(registered, reverse("rescue:case-list"), fetch_redirect_response=False)
        member = get_user_model().objects.get(email="guest-location-journey@example.invalid")
        self.member = member
        self.assert_regular_member()
        self.assertEqual(int(self.guest.session["_auth_user_id"]), member.pk)
        logged_out = self.post_with_csrf(self.guest, reverse("accounts:logout"))
        self.assertEqual(logged_out.status_code, 302)
        self.assertNotIn("_auth_user_id", self.guest.session)
        self.log_in(self.guest, member)
        self.assert_regular_member()
        return member

    def log_in(self, client, user):
        login_url = reverse("accounts:login")
        self.assertEqual(client.get(login_url).status_code, 200)
        response = self.post_with_csrf(client, login_url, {
            "username": user.email, "password": self.password,
        })
        self.assertRedirects(response, reverse("rescue:case-list"), fetch_redirect_response=False)
        self.assertEqual(int(client.session["_auth_user_id"]), user.pk)

    def search_address(self):
        page = self.guest.get(reverse("rescue:case-create"))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["form"].fields["location_confirmed"].required)
        self.assertContains(page, "data-address-search")
        response = self.post_with_csrf(self.guest, reverse("rescue:location-search"), {
            "address": self.point["label"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"results": [self.point]})
        self.provider.assert_called_once_with(self.point["label"], "guest-journey-test-only-key")
        return response.json()["results"][0]

    def report_payload(self, point):
        return {
            "title": "Mèo bị thương trước cổng chợ",
            "animal_type": RescueCase.AnimalType.CAT,
            "urgency": RescueCase.Urgency.HIGH,
            "description": "Mèo bị thương ở chân, đang nằm trước cổng chợ.",
            "address": point["label"],
            "latitude": format(point["latitude"], ".6f"),
            "longitude": format(point["longitude"], ".6f"),
            "contact_name": self.member.full_name,
            "contact_phone": self.member.phone,
            "is_location_private": "on",
        }

    def assert_no_report_side_effects(self):
        self.assertFalse(RescueCase.objects.exists())
        self.assertFalse(RescueCaseImage.objects.exists())
        self.assertFalse(RescueAssignment.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_registered_guest_delivers_confirmed_pin_to_admin_and_assigned_moderator(self):
        point = self.search_address()
        self.assert_no_report_side_effects()
        payload = self.report_payload(point)
        create_url = reverse("rescue:case-create")
        unconfirmed = self.post_with_csrf(self.guest, create_url, payload)
        self.assertEqual(unconfirmed.status_code, 200)
        self.assertIn("location_confirmed", unconfirmed.context["form"].errors)
        self.assert_no_report_side_effects()

        submitted = self.post_with_csrf(self.guest, create_url, {
            **payload, "location_confirmed": "on",
        })
        case = RescueCase.objects.get(reporter=self.member)
        detail_url = reverse("rescue:case-detail", args=(case.pk,))
        self.assertRedirects(submitted, detail_url, fetch_redirect_response=False)
        self.assertEqual(case.address, point["label"])
        self.assertEqual(case.latitude, Decimal("16.067525"))
        self.assertEqual(case.longitude, Decimal("108.224049"))
        self.assertEqual(case.status, RescueCase.Status.REPORTED)
        self.assertTrue(case.is_location_private)
        self.assert_regular_member()

        notice = Notification.objects.get(
            recipient=self.admin, rescue_case=case, kind=Notification.Kind.CASE_REPORTED,
        )
        self.assertEqual(notice.actor_id, self.member.pk)
        self.assertEqual(notice.target_url, detail_url)
        self.assertIn(point["label"], notice.message)
        self.assertFalse(Notification.objects.filter(recipient=self.moderator).exists())

        admin_client = Client(enforce_csrf_checks=True)
        self.log_in(admin_client, self.admin)
        self.assertContains(admin_client.get(reverse("rescue:notification-list")), escape(notice.message))
        admin_detail = admin_client.get(detail_url)
        self.assertContains(admin_detail, point["label"])
        self.assertFalse(admin_detail.context["map_is_approximate"])
        assigned = self.post_with_csrf(
            admin_client, reverse("rescue:case-assign", args=(case.pk,)), {
                "assignee": self.moderator.pk,
                "notes": "Đến đúng ghim người báo đã kiểm tra.",
            },
        )
        self.assertRedirects(assigned, detail_url, fetch_redirect_response=False)
        assignment = RescueAssignment.objects.get(rescue_case=case, assignee=self.moderator)
        self.assertTrue(assignment.is_active)
        self.assertEqual(assignment.assigned_by_id, self.admin.pk)
        self.assertTrue(Notification.objects.filter(
            recipient=self.moderator, rescue_case=case, kind=Notification.Kind.CASE_ASSIGNED,
        ).exists())
        case.refresh_from_db()
        self.assertEqual(case.status, RescueCase.Status.REPORTED)
        self.assertEqual(case.address, point["label"])
        self.assertEqual(case.latitude, Decimal("16.067525"))
        self.assertEqual(case.longitude, Decimal("108.224049"))

        moderator_client = Client(enforce_csrf_checks=True)
        self.log_in(moderator_client, self.moderator)
        detail = moderator_client.get(detail_url)
        self.assertContains(detail, point["label"])
        self.assertEqual(detail.context["map_latitude"], point["latitude"])
        self.assertEqual(detail.context["map_longitude"], point["longitude"])
        self.assertFalse(detail.context["map_is_approximate"])
        self.assertContains(detail, 'data-latitude="16.067525"')
        self.assertContains(detail, 'data-longitude="108.224049"')
        self.assertNotContains(detail, "data-accuracy")
        self.assert_regular_member()

    def test_guest_search_and_report_require_csrf_and_explicit_pin_confirmation(self):
        response = self.guest.post(reverse("rescue:location-search"), {
            "address": self.point["label"],
        })
        self.assertEqual(response.status_code, 403)
        self.provider.assert_not_called()
        point = self.search_address()
        payload = self.report_payload(point)
        create_url = reverse("rescue:case-create")
        response = self.guest.post(create_url, {**payload, "location_confirmed": "on"})
        self.assertEqual(response.status_code, 403)
        self.assert_no_report_side_effects()
        for value in (None, "", "false"):
            with self.subTest(confirmation=value):
                data = dict(payload)
                if value is not None:
                    data["location_confirmed"] = value
                response = self.post_with_csrf(self.guest, create_url, data)
                self.assertEqual(response.status_code, 200)
                self.assertIn("location_confirmed", response.context["form"].errors)
                self.assert_no_report_side_effects()
        self.assert_regular_member()
