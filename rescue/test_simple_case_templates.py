"""Kiểm tra giao diện cứu hộ gọn vẫn giữ thao tác thật và giới hạn theo vai trò."""

from collections import Counter
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from organizations.models import RescueOrganization

from .models import RescueCase


class _CaseMarkup(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.ids = []
        self.forms = []
        self.details = {}
        self.inputs = []
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag == "form":
            self.forms.append(attrs)
        elif tag == "details" and attrs.get("id"):
            self.details[attrs["id"]] = attrs
        elif tag == "input":
            self.inputs.append(attrs)


class SimpleCaseTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="simple-workspace-admin@example.com", password="test-password",
        )
        cls.reporter = users.objects.create_user(
            email="simple-workspace-reporter@example.com", password="test-password",
        )
        cls.case = RescueCase.objects.create(
            title="Tin cứu hộ cần xác minh", description="Con vật đang bị thương.",
            animal_type=RescueCase.AnimalType.CAT,
            address="430 Hùng Vương, Hải Châu, Đà Nẵng",
            latitude="16.054407", longitude="108.202167",
            reporter=cls.reporter, is_location_private=True,
        )
        RescueOrganization.objects.create(
            name="Đội cứu hộ ngoài hệ thống", created_by=cls.admin,
            is_verified=True, phone="0901234567", email="rescue-team@example.com",
        )

    def test_admin_workspace_keeps_real_actions_and_collapses_long_forms(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("rescue:case-detail", args=(self.case.pk,)))
        self.assertEqual(response.status_code, 200)
        markup = _CaseMarkup(response.content.decode())
        actions = {form.get("action"): form.get("method") for form in markup.forms}
        for name in ("case-claim", "case-handoff", "case-update-status", "case-assign"):
            self.assertEqual(actions[reverse(f"rescue:{name}", args=(self.case.pk,))], "post")
        self.assertEqual(actions[reverse("support:open-case-chat", args=(self.case.pk,))], "post")
        for element_id in ("case-review", "case-handoff", "case-assign", "case-history"):
            self.assertNotIn("open", markup.details[element_id])
        self.assertContains(response, reverse("admin:rescue_rescuecase_change", args=(self.case.pk,)) + "?edit=1")
        self.assertContains(response, reverse("admin:rescue_rescuecase_delete", args=(self.case.pk,)))
        self.assertNotContains(response, "onclick=")
        self.assertFalse([value for value, count in Counter(markup.ids).items() if count > 1])

    def test_reporter_sees_status_without_admin_tools_or_unrelated_navigation(self):
        self.client.force_login(self.reporter)
        response = self.client.get(reverse("rescue:case-detail", args=(self.case.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Theo dõi tin báo")
        self.assertContains(response, self.case.address)
        self.assertNotContains(response, 'id="case-review"')
        self.assertNotContains(response, 'id="case-handoff"')
        self.assertNotContains(response, reverse("admin:rescue_rescuecase_delete", args=(self.case.pk,)))
        self.assertNotContains(response, reverse("rescue:knowledge-list"))
        self.assertNotContains(response, reverse("rescue:team"))

    def test_report_form_has_one_coordinate_pair_and_opens_manual_entry_on_error(self):
        self.client.force_login(self.reporter)
        url = reverse("rescue:case-create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        markup = _CaseMarkup(response.content.decode())
        for name in ("latitude", "longitude"):
            self.assertEqual(sum(item.get("name") == name for item in markup.inputs), 1)
        self.assertNotIn("open", markup.details["manual-coordinates"])
        self.assertFalse([value for value, count in Counter(markup.ids).items() if count > 1])

        invalid = self.client.post(url, {
            "title": "Thiếu vị trí", "animal_type": "cat", "urgency": "high",
            "description": "Cần cứu hộ", "address": "Hải Châu, Đà Nẵng",
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertIn("open", _CaseMarkup(invalid.content.decode()).details["manual-coordinates"])
