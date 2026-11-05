"""Kiểm tra các mục tin báo không trùng nhau và biểu đồ chỉ có ba nhóm số liệu."""

import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from .models import RescueAssignment, RescueCase


class PublicStatusGroupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="groups-admin@example.com", password="test-password",
        )
        cls.reporter = users.objects.create_user(
            email="groups-reporter@example.com", password="test-password",
        )
        cls.moderator = users.objects.create_user(
            email="groups-moderator@example.com", password="test-password",
            role=users.Role.MODERATOR,
        )
        cls.member = users.objects.create_user(
            email="groups-member@example.com", password="test-password",
        )
        cls.cases = {}
        for status in RescueCase.Status.values:
            cls.cases[status] = RescueCase.objects.create(
                title=f"Hồ sơ riêng {status}", description="Kiểm tra nhóm xử lý.",
                status=status, reporter=cls.reporter,
                animal_type=(
                    RescueCase.AnimalType.DOG if status == RescueCase.Status.VERIFIED
                    else RescueCase.AnimalType.CAT
                ),
                address=f"Địa chỉ riêng {status}, Hải Châu, Đà Nẵng",
                latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
                is_location_private=True,
            )
        RescueAssignment.objects.create(
            rescue_case=cls.cases[RescueCase.Status.REPORTED],
            assignee=cls.moderator, assigned_by=cls.admin,
        )

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def page(self, status=None, **query):
        if status is not None:
            query["status"] = status
        return self.client.get(reverse("rescue:case-list"), query)

    def case_ids(self, response):
        return {item.pk for item in response.context["page_obj"].object_list}

    def test_four_tabs_partition_cases_without_overlap(self):
        self.client.force_login(self.admin)
        expected = {
            "reported": {self.cases[RescueCase.Status.REPORTED].pk},
            "verified": {
                self.cases[status].pk for status in (
                    RescueCase.Status.VERIFIED, RescueCase.Status.ASSIGNED,
                    RescueCase.Status.IN_PROGRESS, RescueCase.Status.PENDING_REVIEW,
                )
            },
            "rescued": {self.cases[RescueCase.Status.RESCUED].pk},
            "cancelled": {
                self.cases[RescueCase.Status.CANCELLED].pk,
                self.cases[RescueCase.Status.CLOSED].pk,
            },
        }
        seen = set()
        for status, ids in expected.items():
            with self.subTest(tab=status):
                response = self.page(status)
                actual = self.case_ids(response)
                self.assertEqual(actual, ids)
                self.assertFalse(seen & actual)
                seen.update(actual)
                self.assertEqual(response.context["summary"][status], len(ids))
                tabs = re.search(
                    r'<nav class="case-status-tabs".*?</nav>',
                    response.content.decode(), re.DOTALL,
                ).group()
                self.assertEqual(tabs.count("<a "), 4)
                self.assertEqual(tabs.count('aria-current="page"'), 1)
                self.assertNotIn("Đang cần cứu", tabs)
        self.assertEqual(seen, {item.pk for item in self.cases.values()})

    def test_pending_tab_preserves_private_report_visibility_for_every_role(self):
        pending = self.cases[RescueCase.Status.REPORTED]
        for user, allowed in (
            (None, False), (self.member, False), (self.reporter, True),
            (self.moderator, True), (self.admin, True),
        ):
            with self.subTest(user=user.email if user else "guest"):
                if user is None:
                    self.client.logout()
                else:
                    self.client.force_login(user)
                response = self.page("reported")
                self.assertEqual(self.case_ids(response), {pending.pk} if allowed else set())
                self.assertEqual(response.context["summary"]["reported"], int(allowed))
                if not allowed:
                    self.assertNotContains(response, pending.title)
                    self.assertNotContains(response, pending.address)
                statistics = response.context["public_statistics"]
                self.assertEqual(statistics["status_rows"][0], {"label": "Đã xác nhận", "count": 5})
                feed = self.client.get(reverse("rescue:public-statistics-live")).json()
                self.assertEqual(feed["status_rows"], statistics["status_rows"])
                self.assertNotIn(pending.title, str(feed))
                self.assertNotIn(pending.address, str(feed))

    def test_default_and_invalid_filters_show_approved_cases_and_keep_search(self):
        self.client.force_login(self.admin)
        approved = {
            self.cases[status].pk for status in (
                RescueCase.Status.VERIFIED, RescueCase.Status.ASSIGNED,
                RescueCase.Status.IN_PROGRESS, RescueCase.Status.PENDING_REVIEW,
            )
        }
        for status in (None, "unknown", ""):
            response = self.page(status)
            self.assertEqual(response.context["selected_status"], "verified")
            self.assertEqual(self.case_ids(response), approved)
        filtered = self.page("verified", q="Hồ sơ", animal_type="dog")
        self.assertEqual(self.case_ids(filtered), {self.cases[RescueCase.Status.VERIFIED].pk})
        self.assertContains(filtered, 'name="status" value="verified"')
        self.assertContains(filtered, "Các ca đã phê duyệt")

    def test_statistics_table_prints_only_three_groups(self):
        response = self.page()
        statistics = response.context["public_statistics"]
        self.assertEqual(statistics["status_rows"], [
            {"label": "Đã xác nhận", "count": 5},
            {"label": "Đã cứu thành công", "count": 1},
            {"label": "Đã hủy", "count": 2},
        ])
        markup = render_to_string(
            "rescue/_public_statistics.html", {"public_statistics": statistics},
        )
        rows = re.search(r'<tbody data-statistics-status-rows>(.*?)</tbody>', markup, re.DOTALL).group(1)
        self.assertEqual(rows.count("<tr>"), 3)
        for internal_label in ("Đã phân công", "Đang cứu hộ", "Chờ admin duyệt kết quả", "Đã đóng"):
            self.assertNotIn(internal_label, rows)
        self.assertEqual(statistics["total"], 8)
