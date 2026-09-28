import base64
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from rescue.models import Notification, RescueCase

from .models import SupportAttachment, SupportConversation, SupportMessage


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class SupportChatTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.media_override = override_settings(
            MEDIA_ROOT=self.media_directory.name
        )
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="support-user@example.com",
            password="test-password",
            full_name="Support User",
        )
        self.other_user = user_model.objects.create_user(
            email="other-support-user@example.com",
            password="test-password",
            full_name="Other User",
        )
        self.admin = user_model.objects.create_superuser(
            email="support-admin@example.com",
            password="test-password",
            full_name="Support Admin",
        )
        self.collaborator = user_model.objects.create_user(
            email="collaborator@pawrescue.local",
            password="test-password",
            full_name="Cộng tác viên",
            role=user_model.Role.COLLABORATOR,
        )
        self.other_collaborator = user_model.objects.create_user(
            email="other-collaborator@pawrescue.local",
            password="test-password",
            full_name="Cộng tác viên khác",
            role=user_model.Role.COLLABORATOR,
        )

    def send_user_message(
        self,
        body="Tôi cần hỗ trợ về đơn nhận nuôi.",
        attachments=None,
    ):
        self.client.force_login(self.user)
        data = {"body": body}
        if attachments:
            data["attachments"] = attachments
        return self.client.post(reverse("support:chat-send"), data)

    def test_authenticated_user_sees_chat_widget_but_admin_does_not(self):
        self.client.force_login(self.user)
        user_response = self.client.get(reverse("rescue:case-list"))
        self.client.force_login(self.admin)
        admin_response = self.client.get(reverse("rescue:case-list"))

        self.assertContains(user_response, 'id="support-chat"')
        self.assertNotContains(admin_response, 'id="support-chat"')
        self.assertContains(admin_response, "Hộp thư hỗ trợ")

    def test_user_message_creates_conversation_and_notifies_admin(self):
        response = self.send_user_message()

        self.assertEqual(response.status_code, 201)
        conversation = SupportConversation.objects.get(user=self.user)
        message = conversation.messages.get()
        self.assertEqual(message.sender_role, SupportMessage.SenderRole.USER)
        self.assertFalse(message.is_read_by_admin)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin,
                kind=Notification.Kind.SUPPORT_MESSAGE,
            ).exists()
        )

    def test_admin_can_read_reply_and_notify_user(self):
        self.send_user_message("Admin có thể kiểm tra giúp tôi không?")
        conversation = SupportConversation.objects.get(user=self.user)
        self.client.force_login(self.admin)

        inbox_response = self.client.get(
            reverse("support:inbox"),
            {"conversation": conversation.pk},
        )
        reply_response = self.client.post(
            reverse("support:admin-reply", args=(conversation.pk,)),
            {"body": "Mình đã nhận được và đang kiểm tra cho bạn."},
        )

        self.assertEqual(inbox_response.status_code, 200)
        self.assertContains(inbox_response, "Admin có thể kiểm tra")
        self.assertRedirects(
            reply_response,
            reverse("support:inbox") + f"?conversation={conversation.pk}",
        )
        conversation.refresh_from_db()
        self.assertEqual(
            conversation.status,
            SupportConversation.Status.WAITING_USER,
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.user,
                kind=Notification.Kind.SUPPORT_MESSAGE,
            ).exists()
        )

        self.client.force_login(self.user)
        state_response = self.client.get(reverse("support:chat-state"))
        payload = state_response.json()
        self.assertEqual(len(payload["messages"]), 2)
        self.assertTrue(payload["messages"][1]["is_admin"])
        self.assertEqual(
            payload["messages"][1]["body"],
            "Mình đã nhận được và đang kiểm tra cho bạn.",
        )

    def test_admin_can_open_case_reporter_chat_with_one_click(self):
        rescue_case = RescueCase.objects.create(
            title="Mèo bị thương trước cửa hàng",
            description="Cần đội cứu hộ liên hệ để xác minh.",
            animal_type=RescueCase.AnimalType.CAT,
            reporter=self.user,
            address="12 Nguyễn Văn Linh",
            contact_name="Support User",
            contact_phone="0901234567",
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("support:open-case-chat", args=(rescue_case.pk,))
        )

        conversation = SupportConversation.objects.get(user=self.user)
        expected_url = (
            reverse("support:inbox")
            + f"?conversation={conversation.pk}&case={rescue_case.pk}"
        )
        self.assertRedirects(response, expected_url)
        self.assertEqual(conversation.assigned_to, self.admin)
        self.assertIn(f"ca #{rescue_case.pk}", conversation.subject)

        inbox_response = self.client.get(expected_url)
        self.assertContains(inbox_response, "Đang trao đổi về ca")
        self.assertContains(inbox_response, rescue_case.title)
        self.assertContains(inbox_response, "PawRescue liên hệ với bạn")

    def test_open_case_chat_reuses_existing_active_conversation(self):
        self.send_user_message("Tôi đã nhắn trước đó.")
        conversation = SupportConversation.objects.get(user=self.user)
        rescue_case = RescueCase.objects.create(
            title="Chó đi lạc",
            description="Cần liên hệ người báo tin.",
            animal_type=RescueCase.AnimalType.DOG,
            reporter=self.user,
            address="Quận Hải Châu",
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("support:open-case-chat", args=(rescue_case.pk,))
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            SupportConversation.objects.filter(user=self.user).count(),
            1,
        )
        self.assertIn(f"conversation={conversation.pk}", response.url)

    def test_regular_user_cannot_access_admin_inbox_or_reply(self):
        self.send_user_message()
        conversation = SupportConversation.objects.get(user=self.user)

        inbox_response = self.client.get(reverse("support:inbox"))
        reply_response = self.client.post(
            reverse("support:admin-reply", args=(conversation.pk,)),
            {"body": "Không được phép"},
        )

        self.assertEqual(inbox_response.status_code, 403)
        self.assertEqual(reply_response.status_code, 403)
        self.assertEqual(conversation.messages.count(), 1)

    def test_collaborator_has_separate_portal_and_can_reply(self):
        self.send_user_message("Cộng tác viên có thể hỗ trợ không?")
        conversation = SupportConversation.objects.get(user=self.user)
        self.client.force_login(self.collaborator)

        dashboard_response = self.client.get(reverse("collaborators:dashboard"))
        inbox_response = self.client.get(
            reverse("support:inbox"),
            {"conversation": conversation.pk},
        )
        reply_response = self.client.post(
            reverse("support:admin-reply", args=(conversation.pk,)),
            {"body": "Mình là cộng tác viên và đã nhận tin."},
        )

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "Không gian cộng tác viên")
        self.assertEqual(inbox_response.status_code, 200)
        self.assertContains(inbox_response, "Hộp thư PawRescue")
        self.assertRedirects(
            reply_response,
            reverse("support:inbox") + f"?conversation={conversation.pk}",
        )
        conversation.refresh_from_db()
        self.assertEqual(conversation.assigned_to, self.collaborator)

    def test_collaborator_cannot_read_thread_assigned_to_another_operator(self):
        self.send_user_message("Tin riêng cho người đang phụ trách.")
        conversation = SupportConversation.objects.get(user=self.user)
        conversation.assigned_to = self.collaborator
        conversation.save(update_fields=("assigned_to",))

        self.client.force_login(self.other_collaborator)
        inbox_response = self.client.get(
            reverse("support:inbox"),
            {"conversation": conversation.pk},
        )
        reply_response = self.client.post(
            reverse("support:admin-reply", args=(conversation.pk,)),
            {"body": "Không được phép xen vào."},
        )

        self.assertEqual(inbox_response.status_code, 200)
        self.assertNotContains(inbox_response, "Tin riêng cho người đang phụ trách.")
        self.assertEqual(reply_response.status_code, 404)
        self.assertEqual(conversation.messages.count(), 1)

    def test_collaborator_cannot_close_or_reopen_another_operators_thread(self):
        self.send_user_message("Tin do cộng tác viên đầu tiên phụ trách.")
        conversation = SupportConversation.objects.get(user=self.user)
        conversation.assigned_to = self.collaborator
        conversation.save(update_fields=("assigned_to",))

        self.client.force_login(self.other_collaborator)
        close_response = self.client.post(
            reverse("support:close", args=(conversation.pk,))
        )

        self.assertEqual(close_response.status_code, 404)
        conversation.refresh_from_db()
        self.assertNotEqual(conversation.status, SupportConversation.Status.CLOSED)

        conversation.status = SupportConversation.Status.CLOSED
        conversation.save(update_fields=("status",))
        reopen_response = self.client.post(
            reverse("support:reopen", args=(conversation.pk,))
        )

        self.assertEqual(reopen_response.status_code, 404)
        conversation.refresh_from_db()
        self.assertEqual(conversation.status, SupportConversation.Status.CLOSED)

    def test_collaborator_can_close_and_reopen_owned_thread(self):
        self.send_user_message("Hãy đóng rồi mở lại cuộc trò chuyện này.")
        conversation = SupportConversation.objects.get(user=self.user)
        conversation.assigned_to = self.collaborator
        conversation.save(update_fields=("assigned_to",))
        self.client.force_login(self.collaborator)

        close_response = self.client.post(
            reverse("support:close", args=(conversation.pk,))
        )
        conversation.refresh_from_db()

        self.assertRedirects(
            close_response,
            reverse("support:inbox") + f"?conversation={conversation.pk}",
        )
        self.assertEqual(conversation.status, SupportConversation.Status.CLOSED)
        self.assertEqual(conversation.assigned_to, self.collaborator)

        reopen_response = self.client.post(
            reverse("support:reopen", args=(conversation.pk,))
        )
        conversation.refresh_from_db()

        self.assertRedirects(
            reopen_response,
            reverse("support:inbox") + f"?conversation={conversation.pk}",
        )
        self.assertEqual(
            conversation.status,
            SupportConversation.Status.WAITING_ADMIN,
        )
        self.assertEqual(conversation.assigned_to, self.collaborator)

    def test_closed_thread_cannot_reopen_when_user_has_an_active_thread(self):
        self.send_user_message("Cuộc trò chuyện cũ.")
        closed_conversation = SupportConversation.objects.get(user=self.user)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("support:close", args=(closed_conversation.pk,))
        )
        active_conversation = SupportConversation.objects.create(
            user=self.user,
            subject="Cuộc trò chuyện đang hoạt động",
        )

        response = self.client.post(
            reverse("support:reopen", args=(closed_conversation.pk,))
        )

        self.assertRedirects(response, reverse("support:inbox"))
        closed_conversation.refresh_from_db()
        active_conversation.refresh_from_db()
        self.assertEqual(
            closed_conversation.status,
            SupportConversation.Status.CLOSED,
        )
        self.assertNotEqual(
            active_conversation.status,
            SupportConversation.Status.CLOSED,
        )

    def test_plain_staff_user_does_not_gain_support_access(self):
        plain_staff = get_user_model().objects.create_user(
            email="plain-staff@example.com",
            password="test-password",
            full_name="Nhân viên không có quyền hỗ trợ",
            is_staff=True,
        )
        self.client.force_login(plain_staff)

        response = self.client.get(reverse("support:inbox"))

        self.assertEqual(response.status_code, 403)

    def test_sending_after_closed_conversation_starts_a_new_thread(self):
        self.send_user_message("Cuộc trò chuyện đầu tiên")
        first_conversation = SupportConversation.objects.get(user=self.user)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("support:close", args=(first_conversation.pk,))
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("support:chat-send"),
            {"body": "Tôi có câu hỏi mới."},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            SupportConversation.objects.filter(user=self.user).count(),
            2,
        )
        self.assertEqual(
            SupportConversation.objects.filter(
                user=self.user,
            ).exclude(status=SupportConversation.Status.CLOSED).count(),
            1,
        )

    def test_empty_message_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("support:chat-send"),
            {"body": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SupportConversation.objects.exists())

    def test_user_can_send_image_without_text(self):
        image = SimpleUploadedFile(
            "anh-hien-truong.png",
            PNG_1X1,
            content_type="image/png",
        )

        response = self.send_user_message(body="", attachments=[image])

        self.assertEqual(response.status_code, 201)
        message = SupportMessage.objects.get()
        attachment = message.attachments.get()
        self.addCleanup(
            attachment.file.storage.delete,
            attachment.file.name,
        )
        self.assertEqual(message.body, "")
        self.assertEqual(
            attachment.media_type,
            SupportAttachment.MediaType.IMAGE,
        )
        self.assertEqual(attachment.original_name, "anh-hien-truong.png")
        self.assertRegex(attachment.file.name, r"^\d{4}/\d{2}/")
        payload = response.json()["message"]
        self.assertEqual(payload["attachments"][0]["media_type"], "image")
        self.assertEqual(
            payload["attachments"][0]["url"],
            reverse("support:attachment", args=(attachment.pk,)),
        )

        own_file_response = self.client.get(
            reverse("support:attachment", args=(attachment.pk,))
        )
        self.assertEqual(own_file_response.status_code, 200)
        self.assertEqual(own_file_response["X-Content-Type-Options"], "nosniff")

        self.client.force_login(self.other_user)
        denied_response = self.client.get(
            reverse("support:attachment", args=(attachment.pk,))
        )
        self.assertEqual(denied_response.status_code, 404)

    def test_non_media_attachment_is_rejected(self):
        document = SimpleUploadedFile(
            "thong-tin.txt",
            b"not allowed",
            content_type="text/plain",
        )

        response = self.send_user_message(body="", attachments=[document])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SupportConversation.objects.exists())

    def test_admin_can_reply_with_video_attachment(self):
        self.send_user_message("Tôi gửi tình trạng qua video nhé.")
        conversation = SupportConversation.objects.get(user=self.user)
        video = SimpleUploadedFile(
            "phan-hoi.mp4",
            b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom",
            content_type="video/mp4",
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("support:admin-reply", args=(conversation.pk,)),
            {"body": "", "attachments": [video]},
        )

        self.assertRedirects(
            response,
            reverse("support:inbox") + f"?conversation={conversation.pk}",
        )
        admin_message = conversation.messages.get(
            sender_role=SupportMessage.SenderRole.ADMIN,
        )
        admin_attachment = admin_message.attachments.get()
        self.addCleanup(
            admin_attachment.file.storage.delete,
            admin_attachment.file.name,
        )
        self.assertEqual(
            admin_attachment.media_type,
            SupportAttachment.MediaType.VIDEO,
        )

        self.client.force_login(self.user)
        payload = self.client.get(reverse("support:chat-state")).json()
        self.assertEqual(payload["messages"][1]["attachments"][0]["media_type"], "video")

    def test_closed_widget_keeps_admin_reply_unread_until_opened(self):
        self.send_user_message()
        conversation = SupportConversation.objects.get(user=self.user)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("support:admin-reply", args=(conversation.pk,)),
            {"body": "Bạn mở khung chat sẽ thấy tin nhắn này."},
        )
        admin_message = conversation.messages.get(
            sender_role=SupportMessage.SenderRole.ADMIN,
        )

        self.client.force_login(self.user)
        closed_state = self.client.get(reverse("support:chat-state"))
        admin_message.refresh_from_db()

        self.assertEqual(closed_state.status_code, 200)
        self.assertEqual(closed_state.json()["unread_count"], 1)
        self.assertFalse(admin_message.is_read_by_user)

        open_state = self.client.get(
            reverse("support:chat-state"),
            {"mark_read": "1"},
        )
        admin_message.refresh_from_db()

        self.assertEqual(open_state.json()["unread_count"], 0)
        self.assertTrue(admin_message.is_read_by_user)

    def test_admin_inbox_state_returns_new_message_and_marks_it_read(self):
        self.send_user_message("Tin nhắn cần xuất hiện tự động.")
        conversation = SupportConversation.objects.get(user=self.user)
        user_message = conversation.messages.get()
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("support:inbox-state"),
            {"conversation": conversation.pk},
        )
        user_message.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected"]["id"], conversation.pk)
        self.assertEqual(
            payload["selected"]["messages"][0]["body"],
            "Tin nhắn cần xuất hiện tự động.",
        )
        self.assertEqual(payload["conversations"][0]["unread_count"], 0)
        self.assertTrue(user_message.is_read_by_admin)

        self.client.force_login(self.other_user)
        denied_response = self.client.get(reverse("support:inbox-state"))
        self.assertEqual(denied_response.status_code, 403)
