from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import Resolver404, resolve, reverse

from adoptions.models import AnimalProfile

from .models import RescueCase


class DisabledAdoptionRoutesTests(SimpleTestCase):
    def test_adoption_public_and_admin_routes_are_unavailable(self):
        for path in ("/adoptions/", "/adoptions/animals/1/", "/adoptions/dashboard/"):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

        for model in apps.get_app_config("adoptions").get_models():
            with self.subTest(model=model.__name__):
                self.assertFalse(admin.site.is_registered(model))


@override_settings(SECURE_SSL_REDIRECT=False)
class RescueOnlySurfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = get_user_model().objects.create_user(
            email="reporter@example.com", password="test-password"
        )
        cls.admin_user = get_user_model().objects.create_superuser(
            email="operator@example.com", password="test-password"
        )

    def test_public_home_focuses_on_reporting_and_map(self):
        response = self.client.get(reverse("rescue:case-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("rescue:case-create"))
        self.assertContains(response, reverse("rescue:case-map"))
        self.assertNotContains(response, "/adoptions/")
        self.assertContains(response, "/donations/")
        self.assertNotContains(response, "Nhận nuôi")

    def test_profile_and_admin_have_no_adoption_links(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/adoptions/")

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tiếp nhận tin báo")
        self.assertNotContains(response, "adoptions")

    def test_rescued_case_does_not_start_an_adoption_workflow(self):
        case = RescueCase.objects.create(
            title="Động vật đã được giải cứu",
            description="Kết quả đã được ghi nhận.",
            animal_type=RescueCase.AnimalType.CAT,
            address="Đà Nẵng",
            reporter=self.member,
        )
        case.status = RescueCase.Status.RESCUED
        case.save(update_fields=("status",))

        self.assertFalse(AnimalProfile.objects.filter(rescue_case=case).exists())
