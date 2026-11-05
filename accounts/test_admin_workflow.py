"""Kiểm thử biểu mẫu quản trị tài khoản, nhóm quyền và giới hạn của người được ủy quyền."""

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from support.models import SupportConversation, SupportMessage


class AccountAdminWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="account-admin@example.com", password="test-password", full_name="Admin"
        )
        cls.other_admin = users.objects.create_superuser(
            email="other-account-admin@example.com", password="test-password", full_name="Other Admin"
        )
        cls.member = users.objects.create_user(
            email="account-member@example.com", password="test-password", full_name="Member"
        )
        cls.editor = users.objects.create_user(
            email="account-editor@example.com", password="test-password", full_name="Editor", is_staff=True
        )
        cls.editor.user_permissions.add(*Permission.objects.filter(
            content_type__app_label__in=("accounts", "auth"),
            codename__in=("add_user", "view_user", "change_user", "delete_user",
                          "add_group", "view_group", "change_group", "delete_group"),
        ))

    def change_data(self, user, **overrides):
        data = {
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "role": user.role,
            "is_active": "on",
            "date_joined_0": "2026-10-27",
            "date_joined_1": "10:00:00",
            "_save": "Save",
        }
        if user.is_staff:
            data["is_staff"] = "on"
        if user.is_superuser:
            data["is_superuser"] = "on"
        data.update(overrides)
        return data

    def test_admin_header_identifies_accounts_without_legacy_first_name(self):
        self.admin.full_name = ""
        self.admin.save(update_fields=("full_name",))
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertContains(response, f"<strong>{self.admin.email}</strong>", html=True)

    def test_superuser_can_create_edit_reset_password_and_delete_unused_account(self):
        self.client.force_login(self.admin)
        add_url = reverse("admin:accounts_user_add")
        self.assertEqual(self.client.get(add_url).status_code, 200)
        response = self.client.post(add_url, {
            "email": "created-in-admin@example.com",
            "full_name": "Created in Admin", "phone": "0901234567",
            "role": "collaborator", "password1": "Strong-test-password-26",
            "password2": "Strong-test-password-26", "is_active": "on", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        user = get_user_model().objects.get(email="created-in-admin@example.com")
        self.assertTrue(user.check_password("Strong-test-password-26"))
        self.assertEqual(user.role, "collaborator")
        self.assertFalse(user.is_staff)
        change_url = reverse("admin:accounts_user_change", args=(user.pk,))
        self.assertEqual(self.client.get(change_url).status_code, 200)
        response = self.client.post(change_url, self.change_data(user, full_name="Updated Name", is_staff="on"))
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.full_name, "Updated Name")
        self.assertTrue(user.is_staff)
        password_url = reverse("admin:auth_user_password_change", args=(user.pk,))
        response = self.client.post(password_url, {"password1": "Reset-password-2026", "password2": "Reset-password-2026"})
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Reset-password-2026"))
        self.assertTrue(LogEntry.objects.filter(user=self.admin, object_id=str(user.pk)).exists())
        delete_url = reverse("admin:accounts_user_delete", args=(user.pk,))
        self.assertEqual(self.client.get(delete_url).status_code, 200)
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())

    def test_superuser_can_create_update_and_delete_permission_group(self):
        self.client.force_login(self.admin)
        permission = Permission.objects.get(content_type__app_label="support", codename="handle_support")
        response = self.client.post(reverse("admin:auth_group_add"), {
            "name": "Support Operators", "permissions": [permission.pk], "_save": "Save"
        })
        self.assertEqual(response.status_code, 302)
        group = Group.objects.get(name="Support Operators")
        self.assertTrue(group.permissions.filter(pk=permission.pk).exists())
        self.client.post(reverse("admin:accounts_user_change", args=(self.member.pk,)), self.change_data(self.member, groups=[group.pk]))
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("support:inbox")).status_code, 200)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:auth_group_change", args=(group.pk,)), {"name": "Support Renamed", "permissions": [], "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        group.refresh_from_db()
        self.assertEqual(group.name, "Support Renamed")
        self.assertFalse(group.permissions.exists())
        self.assertEqual(self.client.post(reverse("admin:auth_group_delete", args=(group.pk,)), {"post": "yes"}).status_code, 302)
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())

    def test_regular_user_cannot_open_any_account_or_group_admin_page(self):
        self.client.force_login(self.member)
        urls = [
            reverse("admin:index"), reverse("admin:accounts_user_changelist"),
            reverse("admin:accounts_user_add"), reverse("admin:accounts_user_change", args=(self.admin.pk,)),
            reverse("admin:auth_group_changelist"), reverse("admin:auth_group_add"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("admin:login")))

    def test_delegated_editor_cannot_grant_permissions_or_role_via_account_edit(self):
        self.client.force_login(self.editor)
        group = Group.objects.create(name="Privileged group")
        permission = Permission.objects.get(content_type__app_label="support", codename="handle_support")
        for target in (self.member, self.editor):
            with self.subTest(target=target.email):
                response = self.client.post(reverse("admin:accounts_user_change", args=(target.pk,)), self.change_data(
                    target, role="collaborator", is_superuser="on", is_staff="on",
                    groups=[group.pk], user_permissions=[permission.pk], full_name="Edited name",
                ))
                self.assertEqual(response.status_code, 302)
                target.refresh_from_db()
                self.assertFalse(target.is_superuser)
                self.assertEqual(target.role, "member")
                self.assertEqual(target.is_staff, target.pk == self.editor.pk)
                self.assertFalse(target.groups.filter(pk=group.pk).exists())
                self.assertFalse(target.user_permissions.filter(pk=permission.pk).exists())
                self.assertEqual(target.full_name, "Edited name")

    def test_delegated_editor_cannot_create_privileged_account(self):
        self.client.force_login(self.editor)
        response = self.client.post(reverse("admin:accounts_user_add"), {
            "email": "delegated-create@example.com", "full_name": "Delegated",
            "role": "collaborator", "is_staff": "on", "is_superuser": "on", "is_active": "on",
            "password1": "Strong-test-password-26", "password2": "Strong-test-password-26", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        created = get_user_model().objects.get(email="delegated-create@example.com")
        self.assertFalse(created.is_superuser)
        self.assertFalse(created.is_staff)
        self.assertEqual(created.role, "member")

    def test_delegated_editor_cannot_take_over_superuser_or_other_staff(self):
        other_staff = get_user_model().objects.create_user(email="other-staff@example.com", password="Old-password", full_name="Other staff", is_staff=True)
        moderator = get_user_model().objects.create_user(email="protected-moderator@example.com", password="Old-password", role="moderator")
        collaborator = get_user_model().objects.create_user(email="protected-collaborator@example.com", password="Old-password", role="collaborator")
        self.client.force_login(self.editor)
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertNotContains(response, self.admin.email)
        self.assertNotContains(response, other_staff.email)
        self.assertNotContains(response, moderator.email)
        self.assertNotContains(response, collaborator.email)
        for target in (self.admin, self.other_admin, other_staff, moderator, collaborator):
            with self.subTest(target=target.email):
                response = self.client.post(reverse("admin:accounts_user_change", args=(target.pk,)), self.change_data(target, email="takeover@example.com"))
                self.assertEqual(response.status_code, 302)
                target.refresh_from_db()
                self.assertNotEqual(target.email, "takeover@example.com")
                response = self.client.post(reverse("admin:auth_user_password_change", args=(target.pk,)), {"password1": "Takeover-password", "password2": "Takeover-password"})
                self.assertEqual(response.status_code, 404)
                target.refresh_from_db()
                self.assertFalse(target.check_password("Takeover-password"))

    def test_main_admin_can_create_moderator_but_delegated_editor_cannot(self):
        for actor, expected_role in ((self.admin, "moderator"), (self.editor, "member")):
            self.client.force_login(actor)
            email = f"new-moderator-by-{actor.pk}@example.com"
            response = self.client.post(reverse("admin:accounts_user_add"), {
                "email": email, "full_name": "Quản trị viên mới", "role": "moderator",
                "is_staff": "on" if actor == self.editor else "",
                "is_superuser": "on" if actor == self.editor else "",
                "is_active": "on", "password1": "Strong-test-password-26",
                "password2": "Strong-test-password-26", "_save": "Save",
            })
            self.assertEqual(response.status_code, 302)
            created = get_user_model().objects.get(email=email)
            self.assertEqual(created.role, expected_role)
            self.assertFalse(created.is_staff)
            self.assertFalse(created.is_superuser)

    def test_only_main_admin_can_grant_main_admin_privileges(self):
        self.client.force_login(self.editor)
        url = reverse("admin:accounts_user_change", args=(self.member.pk,))
        response = self.client.post(url, self.change_data(self.member, is_staff="on", is_superuser="on"))
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_superuser)
        self.assertFalse(self.member.is_staff)
        self.client.force_login(self.admin)
        response = self.client.post(url, self.change_data(self.member, is_staff="on", is_superuser="on"))
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_superuser)
        self.assertTrue(self.member.is_staff)

    def test_delegated_group_editor_cannot_grant_group_permissions(self):
        group = Group.objects.create(name="Editors")
        self.editor.groups.add(group)
        permission = Permission.objects.get(content_type__app_label="support", codename="handle_support")
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(reverse("admin:auth_group_change", args=(group.pk,))).status_code, 200)
        urls_and_data = [
            (reverse("admin:auth_group_change", args=(group.pk,)), {"name": "Editors", "permissions": [permission.pk]}),
            (reverse("admin:auth_group_add"), {"name": "Escalated", "permissions": [permission.pk]}),
            (reverse("admin:auth_group_delete", args=(group.pk,)), {"post": "yes"}),
        ]
        for url, data in urls_and_data:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, data).status_code, 403)
        self.assertFalse(group.permissions.exists())
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())
        self.assertFalse(Group.objects.filter(name="Escalated").exists())

    def test_admin_login_uses_email_and_rejects_inactive_or_regular_account(self):
        login_url = reverse("admin:login")
        for user in (self.member, self.admin):
            response = self.client.post(login_url, {"username": user.email, "password": "test-password", "next": reverse("admin:index")})
            self.assertEqual(response.status_code, 302 if user.is_superuser else 200)
            self.client.logout()
        self.admin.is_active = False
        self.admin.save(update_fields=("is_active",))
        response = self.client.post(login_url, {"username": self.admin.email, "password": "test-password", "next": reverse("admin:index")})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_account_with_preserved_support_history_is_protected_from_hard_deletion(self):
        conversation = SupportConversation.objects.create(user=self.member)
        SupportMessage.objects.create(conversation=conversation, sender=self.member, sender_role="user", body="Keep audit history")
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:accounts_user_delete", args=(self.member.pk,)), {"post": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(get_user_model().objects.filter(pk=self.member.pk).exists())
        self.assertTrue(SupportMessage.objects.filter(conversation=conversation).exists())
