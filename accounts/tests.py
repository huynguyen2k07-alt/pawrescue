from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
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

    def test_collaborator_dashboard_rejects_regular_user(self):
        user = get_user_model().objects.create_user(
            email="member@example.com",
            password="test-password",
            full_name="Member",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("collaborators:dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_bootstrap_collaborators_is_idempotent_and_non_staff(self):
        first_output = StringIO()
        second_output = StringIO()

        call_command(
            "bootstrap_collaborators",
            count=3,
            domain="pawrescue.test",
            stdout=first_output,
        )
        call_command(
            "bootstrap_collaborators",
            count=3,
            domain="pawrescue.test",
            stdout=second_output,
        )

        user_model = get_user_model()
        collaborators = user_model.objects.filter(
            email__endswith="@pawrescue.test"
        )
        self.assertEqual(collaborators.count(), 3)
        self.assertFalse(collaborators.filter(is_staff=True).exists())
        self.assertFalse(
            collaborators.exclude(role=user_model.Role.COLLABORATOR).exists()
        )
        self.assertIn("tạo 3", first_output.getvalue())
        self.assertIn("đã có 3", second_output.getvalue())
