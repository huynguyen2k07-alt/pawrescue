from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qs, urljoin, urlsplit

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import RescueCase


class LinkParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs).get("href", ""))


@override_settings(SECURE_SSL_REDIRECT=False)
class SimpleRescueCaseListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser(
            email="simple-list-admin@example.com", password="test-password", full_name="Admin kiểm thử"
        )
        cls.matches = []
        for suffix in ("A", "B"):
            cls.matches.append(RescueCase.objects.create(
                title=f"Mèo cần sơ cứu chân trước {suffix}", description="Cần kiểm tra tại hiện trường.",
                animal_type=RescueCase.AnimalType.CAT, address="12 Nguyễn Văn Linh, Đà Nẵng",
                status=RescueCase.Status.REPORTED,
            ))
        cls.wrong_status = RescueCase.objects.create(
            title="Mèo đã sơ cứu chân trước", description="Đã hoàn tất.",
            animal_type=RescueCase.AnimalType.CAT, address="14 Nguyễn Văn Linh, Đà Nẵng",
            status=RescueCase.Status.RESCUED,
        )
        cls.wrong_query = RescueCase.objects.create(
            title="Chó lạc cần tìm chủ", description="Không có vết thương.",
            animal_type=RescueCase.AnimalType.DOG, address="16 Nguyễn Văn Linh, Đà Nẵng",
            status=RescueCase.Status.REPORTED,
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse("admin:rescue_rescuecase_changelist")

    def test_search_and_status_filter_control_the_single_case_table(self):
        response = self.client.get(self.url, {"q": "chân trước", "status__exact": "reported"})
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual([case.pk for case in response.context["cl"].result_list], [case.pk for case in self.matches])
        html = response.content.decode()
        links = LinkParser(html).links
        self.assertEqual(html.count('class="paw-case-row"'), 2)
        self.assertEqual(html.count('<table class="paw-case-table">'), 1)
        self.assertNotContains(response, self.wrong_status.title)
        self.assertNotContains(response, self.wrong_query.title)
        for case in self.matches:
            self.assertEqual(links.count(reverse("rescue:case-detail", args=(case.pk,))), 1)
            self.assertIn(reverse("admin:rescue_rescuecase_delete", args=(case.pk,)), links)
        self.assertNotIn('name="action"', html)
        self.assertNotIn('type="checkbox"', html)

    def test_pagination_preserves_filters_and_empty_status_returns_all_results(self):
        with patch.object(admin.site._registry[RescueCase], "list_per_page", 1):
            first = self.client.get(self.url, {"q": "chân trước", "status__exact": "reported"})
            self.assertEqual(first.status_code, 200)
            self.assertEqual(len(first.context["cl"].result_list), 1)
            links = LinkParser(first.content.decode()).links
            next_page = next(link for link in links if parse_qs(urlsplit(link).query).get("p") == ["2"])
            self.assertEqual(parse_qs(urlsplit(next_page).query), {"q": ["chân trước"], "status__exact": ["reported"], "p": ["2"]})
            second = self.client.get(urljoin(self.url, next_page))
            self.assertEqual(second.status_code, 200)
            first_pk = first.context["cl"].result_list[0].pk
            second_case = second.context["cl"].result_list[0]
            self.assertNotEqual(first_pk, second_case.pk)
            self.assertIn(reverse("rescue:case-detail", args=(second_case.pk,)), LinkParser(second.content.decode()).links)
        all_rows = self.client.get(self.url, {"q": "", "status__exact": ""})
        self.assertEqual(all_rows.context["cl"].result_count, 4)
