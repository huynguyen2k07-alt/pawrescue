"""Kiểm thử quản trị hỗ trợ và quyền riêng tư của hội thoại."""

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from rescue.models import Notification

from .models import SupportAttachment, SupportConversation, SupportMessage


class SupportAdminWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(email="workflow-admin@example.com", password="test-password", full_name="Admin")
        cls.member = users.objects.create_user(email="workflow-member@example.com", password="test-password", full_name="Member")
        cls.other_member = users.objects.create_user(email="other-workflow-member@example.com", password="test-password", full_name="Other Member")
        cls.operator = users.objects.create_user(email="workflow-operator@example.com", password="test-password", full_name="Operator", role="collaborator", is_staff=True)
        cls.other_operator = users.objects.create_user(email="other-workflow-operator@example.com", password="test-password", full_name="Other Operator", role="collaborator", is_staff=True)
        cls.plain_staff = users.objects.create_user(email="workflow-staff@example.com", password="test-password", full_name="Plain Staff", is_staff=True)
        permissions = Permission.objects.filter(content_type__app_label="support")
        for operator in (cls.operator, cls.other_operator):
            operator.user_permissions.add(*permissions)
        cls.plain_staff.user_permissions.add(*permissions.exclude(codename="handle_support"))

    def setUp(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("support:chat-send"), {"body": "Private original request"})
        self.assertEqual(response.status_code, 201)
        self.conversation = SupportConversation.objects.get(user=self.member)
        self.message = self.conversation.messages.get()
        self.client.force_login(self.admin)

    def conversation_data(self, **overrides):
        data = {
            "user": self.member.pk, "subject": self.conversation.subject,
            "status": self.conversation.status, "assigned_to": "", "_save": "Save",
            "messages-TOTAL_FORMS": "0", "messages-INITIAL_FORMS": "0",
            "messages-MIN_NUM_FORMS": "0", "messages-MAX_NUM_FORMS": "0",
        }
        data.update(overrides)
        return data

    def make_attachment(self, message=None):
        item = SupportAttachment.objects.create(
            message=message or self.message, file=ContentFile(b"private-test-media", name="test.png"),
            media_type="image", original_name="test.png", content_type="image/png", size=18,
        )
        self.addCleanup(item.file.storage.delete, item.file.name)
        return item

    def test_superuser_has_support_admin_lists_and_safe_edit_forms(self):
        attachment = self.make_attachment()
        for model_name, obj in (("supportconversation", self.conversation), ("supportmessage", self.message), ("supportattachment", attachment)):
            with self.subTest(model=model_name):
                response = self.client.get(reverse(f"admin:support_{model_name}_changelist"))
                self.assertEqual(response.status_code, 200)
                response = self.client.get(reverse(f"admin:support_{model_name}_change", args=(obj.pk,)))
                self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("admin:support_supportconversation_change", args=(self.conversation.pk,)))
        self.assertContains(response, "Mở hộp thư")
        self.assertContains(response, reverse("support:inbox") + f"?conversation={self.conversation.pk}")

    def test_admin_can_delete_whole_attachment_only_conversation(self):
        self.message.body = ""
        self.message.save(update_fields=("body",))
        self.make_attachment()
        response = self.client.post(
            reverse("admin:support_supportconversation_delete", args=(self.conversation.pk,)),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupportConversation.objects.filter(pk=self.conversation.pk).exists())

    def test_admin_can_delete_whole_attachment_only_message(self):
        self.message.body = ""
        self.message.save(update_fields=("body",))
        self.make_attachment()
        response = self.client.post(
            reverse("admin:support_supportmessage_delete", args=(self.message.pk,)),
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupportMessage.objects.filter(pk=self.message.pk).exists())

    def test_admin_can_bulk_delete_attachment_only_conversations(self):
        self.message.body = ""
        self.message.save(update_fields=("body",))
        self.make_attachment()
        response = self.client.post(reverse("admin:support_supportconversation_changelist"), {
            "action": "delete_selected", "_selected_action": [self.conversation.pk], "post": "yes",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupportConversation.objects.filter(pk=self.conversation.pk).exists())

    def test_superuser_can_add_conversation_and_choose_permission_based_active_operator(self):
        permitted_operator = get_user_model().objects.create_user(email="permission-operator@example.com", password="test-password", full_name="Permitted Operator")
        permitted_operator.user_permissions.add(Permission.objects.get(content_type__app_label="support", codename="handle_support"))
        inactive = get_user_model().objects.create_user(email="inactive-operator@example.com", password="test-password", full_name="Inactive Operator", role="collaborator", is_active=False)
        add_url = reverse("admin:support_supportconversation_add")
        form = self.client.get(add_url).context["adminform"].form
        self.assertIn(permitted_operator, form.fields["assigned_to"].queryset)
        self.assertNotIn(inactive, form.fields["assigned_to"].queryset)
        response = self.client.post(add_url, self.conversation_data(user=self.other_member.pk, assigned_to=permitted_operator.pk, subject="Created by admin"))
        self.assertEqual(response.status_code, 302, response.context["adminform"].form.errors if response.status_code == 200 else "")
        created = SupportConversation.objects.get(user=self.other_member)
        self.assertEqual(created.assigned_to, permitted_operator)
        self.assertEqual(created.subject, "Created by admin")

    def test_duplicate_active_conversation_admin_submission_shows_validation(self):
        response = self.client.post(reverse("admin:support_supportconversation_add"), self.conversation_data())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["adminform"].form.errors)
        self.assertEqual(SupportConversation.objects.filter(user=self.member).count(), 1)

    def test_conversation_owner_and_status_cannot_be_changed_by_forged_admin_post(self):
        response = self.client.post(reverse("admin:support_supportconversation_change", args=(self.conversation.pk,)), self.conversation_data(
            user=self.other_member.pk, status="closed", subject="Corrected subject", assigned_to=self.operator.pk,
            **{"messages-TOTAL_FORMS": "1", "messages-INITIAL_FORMS": "1", "messages-0-id": self.message.pk,
               "messages-0-conversation": self.conversation.pk}
        ))
        self.assertEqual(response.status_code, 302)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.user, self.member)
        self.assertEqual(self.conversation.status, "waiting_admin")
        self.assertEqual(self.conversation.subject, "Corrected subject")
        self.assertEqual(self.conversation.assigned_to, self.operator)

    def test_message_body_correction_keeps_sender_conversation_read_flags_and_logs_edit(self):
        different_conversation = SupportConversation.objects.create(user=self.other_member)
        response = self.client.post(reverse("admin:support_supportmessage_change", args=(self.message.pk,)), {
            "body": "Corrected request text", "conversation": different_conversation.pk,
            "sender": self.admin.pk, "sender_role": "admin", "is_read_by_admin": "on", "is_read_by_user": "", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        self.message.refresh_from_db()
        self.assertEqual(self.message.body, "Corrected request text")
        self.assertEqual(self.message.sender, self.member)
        self.assertEqual(self.message.conversation, self.conversation)
        self.assertEqual(self.message.sender_role, "user")
        self.assertFalse(self.message.is_read_by_admin)
        self.assertTrue(self.message.is_read_by_user)
        entry = LogEntry.objects.filter(
            user=self.admin,
            content_type__app_label="support",
            content_type__model="supportmessage",
            object_id=str(self.message.pk),
        ).latest("action_time")
        self.assertIn("body", entry.change_message.casefold())

    def test_message_correction_cannot_remove_its_only_content(self):
        response = self.client.post(reverse("admin:support_supportmessage_change", args=(self.message.pk,)), {"body": "   ", "_save": "Save"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("body", response.context["adminform"].form.errors)
        self.message.refresh_from_db()
        self.assertEqual(self.message.body, "Private original request")

    def test_attachment_only_message_can_keep_blank_body_during_edit(self):
        self.make_attachment()
        response = self.client.post(reverse("admin:support_supportmessage_change", args=(self.message.pk,)), {"body": "", "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        self.message.refresh_from_db()
        self.assertEqual(self.message.body, "")

    def test_raw_admin_add_cannot_impersonate_a_sender_or_inject_attachment_metadata(self):
        for model_name, data in (
            ("supportmessage", {"conversation": self.conversation.pk, "sender": self.other_member.pk, "sender_role": "user", "body": "Forged"}),
            ("supportattachment", {"message": self.message.pk, "file": "some-private-path"}),
        ):
            with self.subTest(model=model_name):
                self.assertEqual(self.client.post(reverse(f"admin:support_{model_name}_add"), data).status_code, 403)
        self.assertEqual(SupportMessage.objects.count(), 1)
        self.assertFalse(SupportAttachment.objects.exists())

    def test_attachment_admin_uses_authenticated_download_endpoint(self):
        attachment = self.make_attachment()
        response = self.client.get(reverse("admin:support_supportattachment_change", args=(attachment.pk,)))
        self.assertContains(response, reverse("support:attachment", args=(attachment.pk,)))
        with self.assertRaises(ValueError):
            attachment.file.url
        self.assertNotContains(response, str(attachment.file.storage.location))
        download = self.client.get(reverse("support:attachment", args=(attachment.pk,)))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"private-test-media")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")

    def test_admin_can_delete_attachment_when_message_retains_text(self):
        attachment = self.make_attachment()
        response = self.client.post(reverse("admin:support_supportattachment_delete", args=(attachment.pk,)), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupportAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertTrue(SupportMessage.objects.filter(pk=self.message.pk).exists())

    def test_last_attachment_of_blank_message_cannot_be_deleted_individually_or_in_bulk(self):
        attachment = self.make_attachment()
        self.message.body = ""
        self.message.save(update_fields=("body",))
        response = self.client.post(reverse("admin:support_supportattachment_delete", args=(attachment.pk,)), {"post": "yes"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("admin:support_supportattachment_changelist"), {"action": "delete_selected", "_selected_action": [attachment.pk], "post": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(SupportAttachment.objects.filter(pk=attachment.pk).exists())

    def test_superuser_can_delete_message_and_conversation_history(self):
        second_message = SupportMessage.objects.create(conversation=self.conversation, sender=self.admin, sender_role="admin", body="Reply")
        response = self.client.post(reverse("admin:support_supportmessage_delete", args=(second_message.pk,)), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupportMessage.objects.filter(pk=second_message.pk).exists())
        response = self.client.post(reverse("admin:support_supportconversation_delete", args=(self.conversation.pk,)), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SupportConversation.objects.filter(pk=self.conversation.pk).exists())
        self.assertFalse(SupportMessage.objects.filter(pk=self.message.pk).exists())

    def test_support_admin_permissions_do_not_bypass_assigned_conversation_privacy(self):
        attachment = self.make_attachment()
        self.conversation.assigned_to = self.operator
        self.conversation.save(update_fields=("assigned_to",))
        self.client.force_login(self.other_operator)
        for model_name, obj in (("supportconversation", self.conversation), ("supportmessage", self.message), ("supportattachment", attachment)):
            with self.subTest(model=model_name):
                response = self.client.get(reverse(f"admin:support_{model_name}_changelist"))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Private original request")
                self.assertEqual(response.context["cl"].result_count, 0)
                response = self.client.get(reverse(f"admin:support_{model_name}_change", args=(obj.pk,)))
                self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("support:attachment", args=(attachment.pk,))).status_code, 404)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("admin:support_supportmessage_change", args=(self.message.pk,))).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:support_supportmessage_change", args=(self.message.pk,))).status_code, 200)

    def test_plain_staff_with_model_permissions_cannot_read_private_support_history(self):
        self.client.force_login(self.plain_staff)
        response = self.client.get(reverse("admin:support_supportmessage_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cl"].result_count, 0)
        self.assertNotContains(response, "Private original request")
        self.assertEqual(self.client.get(reverse("support:inbox")).status_code, 403)

    def test_new_assigned_thread_message_notifies_only_assignee_and_superusers(self):
        self.conversation.assigned_to = self.operator
        self.conversation.save(update_fields=("assigned_to",))
        Notification.objects.all().delete()
        self.client.force_login(self.member)
        response = self.client.post(reverse("support:chat-send"), {"body": "Assigned private follow up"})
        self.assertEqual(response.status_code, 201)
        recipients = set(Notification.objects.filter(kind=Notification.Kind.SUPPORT_MESSAGE).values_list("recipient_id", flat=True))
        self.assertEqual(recipients, {self.admin.pk, self.operator.pk})
        self.assertFalse(Notification.objects.filter(recipient=self.other_operator).exists())

    def test_regular_user_cannot_reassign_close_reopen_reply_or_use_raw_admin(self):
        self.client.force_login(self.member)
        for name, data in (("admin-reply", {"body": "Fake operator"}), ("close", {}), ("reopen", {})):
            with self.subTest(endpoint=name):
                self.assertEqual(self.client.post(reverse(f"support:{name}", args=(self.conversation.pk,)), data).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:support_supportconversation_changelist")).status_code, 302)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.status, "waiting_admin")
        self.assertIsNone(self.conversation.assigned_to_id)
        self.assertEqual(self.conversation.messages.count(), 1)

    def test_write_endpoints_enforce_csrf_and_post(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.member)
        self.assertEqual(csrf_client.post(reverse("support:chat-send"), {"body": "Without CSRF"}).status_code, 403)
        for name in ("admin-reply", "close", "reopen"):
            with self.subTest(endpoint=name):
                self.assertEqual(self.client.get(reverse(f"support:{name}", args=(self.conversation.pk,))).status_code, 405)
        self.assertEqual(self.client.get(reverse("support:chat-send")).status_code, 405)
        self.assertEqual(SupportMessage.objects.count(), 1)

    def test_invalid_or_excessive_uploads_do_not_create_messages_or_files(self):
        from .tests import PNG_1X1

        invalid_uploads = [
            [SimpleUploadedFile("spoof.png", b"<script>alert(1)</script>", content_type="image/png")],
            [SimpleUploadedFile("spoof.mp4", b"not a video", content_type="video/mp4")],
            [SimpleUploadedFile("wrong-type.png", PNG_1X1, content_type="text/html")],
            [SimpleUploadedFile("unsupported.gif", b"GIF89a", content_type="image/gif")],
            [SimpleUploadedFile(f"image-{index}.png", PNG_1X1, content_type="image/png") for index in range(5)],
        ]
        self.client.force_login(self.member)
        for files in invalid_uploads:
            with self.subTest(files=[file.name for file in files]):
                response = self.client.post(reverse("support:chat-send"), {"body": "", "attachments": files})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.conversation.messages.count(), 1)
                self.assertFalse(SupportAttachment.objects.exists())

    def test_deleted_private_file_returns_not_found_without_exposing_storage_path(self):
        attachment = self.make_attachment()
        attachment.file.storage.delete(attachment.file.name)
        response = self.client.get(reverse("support:attachment", args=(attachment.pk,)))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, str(attachment.file.storage.location), status_code=404)

    def test_closed_conversation_rejects_reply_and_duplicate_close_notification(self):
        self.client.post(reverse("support:close", args=(self.conversation.pk,)))
        count = Notification.objects.filter(recipient=self.member).count()
        response = self.client.post(reverse("support:admin-reply", args=(self.conversation.pk,)), {"body": "Reply after close"})
        self.assertEqual(response.status_code, 302)
        self.client.post(reverse("support:close", args=(self.conversation.pk,)))
        self.assertEqual(self.conversation.messages.count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.member).count(), count)

    def test_messages_remain_plain_text_in_server_rendered_inbox(self):
        self.message.body = '<img src="x" onerror="alert(1)">'
        self.message.save(update_fields=("body",))
        response = self.client.get(reverse("support:inbox"), {"conversation": self.conversation.pk})
        self.assertContains(response, "&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;")
        self.assertNotContains(response, '<img src="x" onerror="alert(1)">')
