"""Kiểm tra hộp thư chỉ hiện đúng phần được admin giao, không hiện hàng đợi riêng."""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from rescue.models import Notification, RescueAssignment, RescueCase

from .models import SupportAttachment, SupportConversation, SupportMessage


@override_settings(SECURE_SSL_REDIRECT=False, MAPTILER_API_KEY="")
class SupportAssignmentPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="support-private-admin@example.invalid", password="test-password",
        )
        cls.operator = users.objects.create_user(
            email="support-private-operator@example.invalid", password="test-password",
            role=users.Role.COLLABORATOR, is_staff=True,
        )
        cls.other_operator = users.objects.create_user(
            email="support-other-operator@example.invalid", password="test-password",
            role=users.Role.COLLABORATOR,
        )
        cls.users = [users.objects.create_user(
            email=f"support-private-client-{index}@example.invalid", password="test-password",
            full_name=f"Người dùng thử {index}", phone=f"091234567{index}",
        ) for index in range(3)]
        cls.unassigned = SupportConversation.objects.create(user=cls.users[0])
        cls.owned = SupportConversation.objects.create(user=cls.users[1], assigned_to=cls.operator)
        cls.other = SupportConversation.objects.create(user=cls.users[2], assigned_to=cls.other_operator)
        cls.unassigned_message = SupportMessage.objects.create(
            conversation=cls.unassigned, sender=cls.users[0],
            sender_role=SupportMessage.SenderRole.USER,
            body="AUDIT-UNASSIGNED-SECRET-7593",
        )
        cls.owned_message = SupportMessage.objects.create(
            conversation=cls.owned, sender=cls.users[1],
            sender_role=SupportMessage.SenderRole.USER, body="AUDIT-OWN-ASSIGNED-5928",
        )
        cls.other_message = SupportMessage.objects.create(
            conversation=cls.other, sender=cls.users[2],
            sender_role=SupportMessage.SenderRole.USER, body="AUDIT-OTHER-ASSIGNED-8712",
        )
        permissions = Permission.objects.filter(content_type__app_label="support")
        cls.operator.user_permissions.add(*permissions)

    def setUp(self):
        directory = self.enterContext(TemporaryDirectory(prefix="pawrescue-support-private-"))
        self.enterContext(override_settings(PRIVATE_SUPPORT_MEDIA_ROOT=Path(directory)))
        self.attachment = SupportAttachment.objects.create(
            message=self.unassigned_message,
            file=ContentFile(b"audit-private-file-fixture", name="private.png"),
            media_type=SupportAttachment.MediaType.IMAGE,
            original_name="private.png", content_type="image/png", size=26,
        )

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_operator_inbox_and_poll_hide_unassigned_and_other_conversations(self):
        client = self.client_for(self.operator)
        response = client.get(reverse("support:inbox"), {"conversation": self.unassigned.pk})
        self.assertContains(response, self.owned_message.body)
        self.assertNotContains(response, self.unassigned_message.body)
        self.assertNotContains(response, self.other_message.body)
        self.assertNotContains(response, self.users[0].email)
        self.assertNotContains(response, self.users[0].phone)
        state = client.get(reverse("support:inbox-state"), {
            "conversation": self.unassigned.pk,
        }).json()
        self.assertEqual([item["id"] for item in state["conversations"]], [self.owned.pk])
        self.assertEqual(state["selected"]["id"], self.owned.pk)
        self.unassigned_message.refresh_from_db()
        self.assertFalse(self.unassigned_message.is_read_by_admin)

    def test_unassigned_threads_cannot_be_replied_closed_or_reopened_by_operator(self):
        client = self.client_for(self.operator)
        for action, data in (("admin-reply", {"body": "Không được ghi"}), ("close", {}), ("reopen", {})):
            with self.subTest(action=action):
                response = client.post(reverse(f"support:{action}", args=(self.unassigned.pk,)), data)
                self.assertEqual(response.status_code, 404)
        self.unassigned.refresh_from_db()
        self.assertIsNone(self.unassigned.assigned_to_id)
        self.assertEqual(self.unassigned.messages.count(), 1)

    def test_case_assignment_does_not_claim_entire_unassigned_support_history(self):
        case = RescueCase.objects.create(
            title="Ca đã giao", description="Nội dung riêng", animal_type="cat",
            address="Địa chỉ riêng", reporter=self.users[0],
        )
        RescueAssignment.objects.create(rescue_case=case, assignee=self.operator, assigned_by=self.admin)
        response = self.client_for(self.operator).post(reverse("support:open-case-chat", args=(case.pk,)))
        self.assertEqual(response.status_code, 302)
        self.unassigned.refresh_from_db()
        self.assertIsNone(self.unassigned.assigned_to_id)
        self.assertEqual(SupportConversation.objects.filter(user=self.users[0]).count(), 1)

    def test_dashboard_and_global_unread_counter_only_include_owned_threads(self):
        response = self.client_for(self.operator).get(reverse("collaborators:dashboard"))
        self.assertEqual(response.context["open_conversation_count"], 1)
        self.assertEqual(response.context["unread_message_count"], 1)
        self.assertEqual(response.context["support_admin_unread_count"], 1)
        self.assertEqual([item.pk for item in response.context["recent_conversations"]], [self.owned.pk])

    def test_admin_can_view_unassigned_and_all_assigned_conversations(self):
        client = self.client_for(self.admin)
        response = client.get(reverse("support:inbox"), {"conversation": self.unassigned.pk})
        self.assertContains(response, self.unassigned_message.body)
        state = client.get(reverse("support:inbox-state")).json()
        self.assertEqual({item["id"] for item in state["conversations"]}, {
            self.unassigned.pk, self.owned.pk, self.other.pk,
        })

    def test_new_unassigned_client_message_only_notifies_main_admin(self):
        response = self.client_for(self.users[0]).post(reverse("support:chat-send"), {
            "body": "Nội dung riêng không gửi cả đội.",
        })
        self.assertEqual(response.status_code, 201)
        notices = Notification.objects.filter(kind=Notification.Kind.SUPPORT_MESSAGE)
        self.assertEqual(set(notices.values_list("recipient_id", flat=True)), {self.admin.pk})

    def test_assigned_client_message_notifies_only_assigned_operator_and_admin(self):
        response = self.client_for(self.users[1]).post(reverse("support:chat-send"), {"body": "Đúng người phụ trách."})
        self.assertEqual(response.status_code, 201)
        notices = Notification.objects.filter(kind=Notification.Kind.SUPPORT_MESSAGE)
        self.assertEqual(set(notices.values_list("recipient_id", flat=True)), {self.admin.pk, self.operator.pk})

    def test_unassigned_attachment_denied_to_operator_and_other_client(self):
        url = reverse("support:attachment", args=(self.attachment.pk,))
        for user in (self.operator, self.other_operator, self.users[1]):
            with self.subTest(user=user):
                self.assertEqual(self.client_for(user).get(url).status_code, 404)

    def test_owner_and_admin_attachment_access_uses_no_store(self):
        url = reverse("support:attachment", args=(self.attachment.pk,))
        for user in (self.admin, self.users[0]):
            with self.subTest(user=user):
                response = self.client_for(user).get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers.get("Cache-Control", ""))
                self.assertEqual(b"".join(response.streaming_content), b"audit-private-file-fixture")

    def test_explicitly_assigned_operator_can_read_attachment_and_reply(self):
        self.unassigned.assigned_to = self.operator
        self.unassigned.save(update_fields=("assigned_to",))
        client = self.client_for(self.operator)
        response = client.get(reverse("support:attachment", args=(self.attachment.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"audit-private-file-fixture")
        response = client.post(reverse("support:admin-reply", args=(self.unassigned.pk,)), {"body": "Đã nhận thông tin."})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.unassigned.messages.filter(sender=self.operator).exists())

    def test_staff_admin_views_do_not_offer_unassigned_records_or_ownership_forgery(self):
        client = self.client_for(self.operator)
        response = client.get(reverse("admin:support_supportconversation_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.users[0].email)
        response = client.get(reverse("admin:support_supportconversation_change", args=(self.unassigned.pk,)))
        self.assertEqual(response.status_code, 302)
        response = client.get(reverse("admin:support_supportconversation_add"))
        self.assertEqual(response.status_code, 403)
        response = client.get(reverse("admin:support_supportconversation_change", args=(self.owned.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("assigned_to", response.context["adminform"].form.fields)

    def test_private_widget_and_inbox_responses_cannot_be_cached(self):
        for user, name in ((self.users[0], "chat-state"), (self.operator, "inbox"), (self.operator, "inbox-state")):
            with self.subTest(endpoint=name):
                response = self.client_for(user).get(reverse(f"support:{name}"))
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response.headers.get("Cache-Control", ""))
                self.assertIn("cookie", response.headers.get("Vary", "").lower())
