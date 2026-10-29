from collections import Counter
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import RescueCase


class _PageIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        element_id = dict(attrs).get("id")
        if element_id:
            self.ids.append(element_id)


class CaseWorkflowFormTests(TestCase):
    def test_update_and_review_labels_target_distinct_inputs(self):
        admin = get_user_model().objects.create_superuser(
            email="workflow-labels@example.com", password="test-password"
        )
        case = RescueCase.objects.create(
            title="Separate field report and final assessment",
            description="The admin must be able to focus either note field.",
            animal_type=RescueCase.AnimalType.CAT,
            address="Hải Châu, Đà Nẵng",
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("rescue:case-detail", args=(case.pk,)))
        self.assertEqual(response.status_code, 200)
        page = _PageIds()
        page.feed(response.content.decode())
        duplicates = [value for value, count in Counter(page.ids).items() if count > 1]
        self.assertEqual(duplicates, [])
        self.assertContains(response, 'for="id_update_note"')
        self.assertContains(response, 'for="id_status_note"')
