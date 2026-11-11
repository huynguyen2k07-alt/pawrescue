"""Đổi tên hiển thị của cộng tác viên không làm đổi hoặc mở rộng quyền tài khoản."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from rescue.models import RescueAssignment, RescueCase
from rescue.permissions import is_rescue_moderator

from .permissions import is_support_operator


@override_settings(SECURE_SSL_REDIRECT=False)
class RescueHelperIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="helper-label-admin@example.com", password="test-password", full_name="Admin chính",
        )
        cls.helper = users.objects.create_user(
            email="helper-label-center@example.com", password="test-password",
            full_name="Trung tâm cứu hộ thử", role=users.Role.MODERATOR,
        )
        cls.support = users.objects.create_user(
            email="helper-label-support@example.com", password="test-password",
            full_name="Nhân viên hỗ trợ thử", role=users.Role.COLLABORATOR,
        )
        cls.editor = users.objects.create_user(
            email="helper-label-editor@example.com", password="test-password",
            full_name="Nhân viên sửa tài khoản", is_staff=True,
        )
        cls.editor.user_permissions.add(Permission.objects.get(
            content_type__app_label="accounts", codename="change_user",
        ))

    def test_helper_and_support_identities_stay_separate_with_existing_role_values(self):
        self.helper.refresh_from_db()
        self.support.refresh_from_db()
        self.assertEqual(self.helper.role, "moderator")
        self.assertEqual(self.helper.get_role_display(), "Cộng tác viên cứu hộ")
        self.assertTrue(is_rescue_moderator(self.helper))
        self.assertFalse(is_support_operator(self.helper))
        self.assertFalse(self.helper.is_staff)
        self.assertFalse(self.helper.is_superuser)
        self.assertEqual(self.support.role, "collaborator")
        self.assertEqual(self.support.get_role_display(), "Nhân viên hỗ trợ")
        self.assertTrue(is_support_operator(self.support))

    def test_admin_creation_form_explains_distinct_roles_for_people_and_centers(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:accounts_user_add"))
        self.assertContains(response, '<option value="moderator">Cộng tác viên cứu hộ</option>', html=True)
        self.assertContains(response, '<option value="collaborator">Nhân viên hỗ trợ</option>', html=True)
        self.assertContains(response, "cá nhân hoặc trung tâm")
        self.assertContains(response, "chỉ xử lý ca được giao")

    def test_existing_helper_keeps_assignment_and_sees_clear_workspace_and_profile_labels(self):
        case = RescueCase.objects.create(
            title="Ca giao cho trung tâm", description="Theo dõi ca thử",
            animal_type=RescueCase.AnimalType.CAT, address="Địa chỉ ca được giao",
        )
        assignment = RescueAssignment.objects.create(
            rescue_case=case, assignee=self.helper, assigned_by=self.admin,
        )
        self.client.force_login(self.helper)
        response = self.client.get(reverse("collaborators:dashboard"))
        self.assertContains(response, "Cộng tác viên cứu hộ")
        self.assertContains(response, case.title)
        self.assertNotContains(response, reverse("support:inbox"))
        self.assertContains(self.client.get(reverse("accounts:profile")), "Cộng tác viên cứu hộ")
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)
        self.assertEqual(assignment.assignee_id, self.helper.pk)

    def test_self_registration_cannot_choose_helper_or_admin_privileges(self):
        response = self.client.post(reverse("accounts:register"), {
            "email": "helper-label-registered@example.com", "full_name": "Người dùng mới",
            "password1": "Secure-test-password-2026", "password2": "Secure-test-password-2026",
            "role": "moderator", "is_staff": "on", "is_superuser": "on",
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email="helper-label-registered@example.com")
        self.assertEqual(user.role, user.Role.MEMBER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(is_rescue_moderator(user))

    def test_only_main_admin_can_promote_member_to_rescue_helper(self):
        users = get_user_model()
        member = users.objects.create_user(
            email="helper-label-promote@example.com", password="test-password", full_name="Sắp được giao ca",
        )
        url = reverse("admin:accounts_user_change", args=(member.pk,))
        payload = {
            "email": member.email, "full_name": member.full_name, "role": "moderator",
            "is_active": "on", "date_joined_0": "2026-11-10", "date_joined_1": "10:00:00",
            "_save": "Lưu",
        }
        self.client.force_login(self.editor)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.role, users.Role.MEMBER)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        member.refresh_from_db()
        self.assertEqual(member.role, users.Role.MODERATOR)
        self.assertEqual(member.get_role_display(), "Cộng tác viên cứu hộ")
        self.assertFalse(member.is_staff)
        self.assertFalse(member.is_superuser)
        self.assertFalse(is_support_operator(member))
