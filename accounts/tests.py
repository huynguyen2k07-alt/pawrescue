from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AccountViewTests(TestCase):
    def test_registration_creates_user_and_logs_them_in(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "email": "new-user@example.com",
                "full_name": "New User",
                "phone": "0901234567",
                "password1": "A-strong-password-2026",
                "password2": "A-strong-password-2026",
            },
        )

        self.assertRedirects(response, reverse("rescue:case-list"))
        user = get_user_model().objects.get(email="new-user@example.com")
        self.assertEqual(user.full_name, "New User")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:profile')}",
        )
