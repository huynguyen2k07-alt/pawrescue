from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from rescue.models import RescueAssignment, RescueCase
from .models import SupportConversation


@override_settings(SECURE_SSL_REDIRECT=False)
class SupportCaseContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(email="context-admin@example.com", password="test-password")
        cls.operator = users.objects.create_user(email="context-operator@example.com", password="test-password", role=users.Role.COLLABORATOR)
        cls.reporter = users.objects.create_user(email="context-reporter@example.com", password="test-password")
        cls.other_reporter = users.objects.create_user(email="context-other@example.com", password="test-password")
        cls.case = RescueCase.objects.create(
            title="Ca riêng tư đang trao đổi", animal_type="cat", description="Cần hỗ trợ.",
            reporter=cls.reporter, address="Địa chỉ hiện trường riêng tư", is_location_private=True,
        )
        cls.other_case = RescueCase.objects.create(
            title="Ca của người khác", animal_type="dog", description="Ca khác.",
            reporter=cls.other_reporter, address="Địa chỉ khác", is_location_private=True,
        )
        cls.conversation = SupportConversation.objects.create(user=cls.reporter, assigned_to=cls.operator)

    def inbox_url(self, case=None):
        return reverse("support:inbox") + f"?conversation={self.conversation.pk}&case={(case or self.case).pk}"

    def test_admin_reply_keeps_case_link_and_clears_initial_draft(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.inbox_url())
        self.assertEqual(response.context["context_case"], self.case)
        self.assertContains(response, f'name="case" value="{self.case.pk}"')
        response = self.client.post(reverse("support:admin-reply", args=(self.conversation.pk,)), {
            "body": "Đã tiếp nhận yêu cầu và đang điều phối.", "case": self.case.pk,
        }, follow=True)
        self.assertEqual(response.context["context_case"], self.case)
        self.assertEqual(response.context["draft_message"], "")
        self.assertContains(response, reverse("admin:rescue_rescuecase_change", args=(self.case.pk,)))

    def test_conversation_operator_cannot_reveal_unassigned_private_case(self):
        self.client.force_login(self.operator)
        response = self.client.get(self.inbox_url())
        self.assertIsNone(response.context["context_case"])
        self.assertNotContains(response, self.case.address)
        self.assertNotContains(response, self.case.title)
        RescueAssignment.objects.create(rescue_case=self.case, assignee=self.operator, assigned_by=self.admin)
        response = self.client.get(self.inbox_url())
        self.assertEqual(response.context["context_case"], self.case)
        self.assertContains(response, reverse("rescue:case-detail", args=(self.case.pk,)))

    def test_reply_rejects_case_context_belonging_to_different_reporter(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.inbox_url(self.other_case))
        self.assertIsNone(response.context["context_case"])
        response = self.client.post(reverse("support:admin-reply", args=(self.conversation.pk,)), {
            "body": "Phản hồi chung không gắn ca của người khác.", "case": self.other_case.pk,
        })
        self.assertEqual(response.url, reverse("support:inbox") + f"?conversation={self.conversation.pk}")
