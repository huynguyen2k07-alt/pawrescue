import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from rescue.models import Notification, RescueCase

from .models import SupportAttachment, SupportConversation, SupportMessage


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

        self.assertEqual(inbox_response.status_code, 302)
        self.assertEqual(reply_response.status_code, 302)
        self.assertEqual(conversation.messages.count(), 1)

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
            "anh-hien-truong.jpg",
            b"test-image-content",
            content_type="image/jpeg",
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
        self.assertEqual(attachment.original_name, "anh-hien-truong.jpg")
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
            b"test-video-content",
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
        self.assertEqual(denied_response.status_code, 302)
