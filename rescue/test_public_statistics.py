"""Kiểm tra số liệu công khai, mốc ngày và bộ nhớ đệm của biểu đồ cứu hộ."""

import base64
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import RescueCase
from .statistics import get_public_rescue_statistics


@override_settings(TIME_ZONE="Asia/Ho_Chi_Minh")
class PublicRescueStatisticsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = datetime(2026, 10, 31, 5, tzinfo=datetime_timezone.utc)
        clock = patch("rescue.statistics.timezone.now", return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.addCleanup(cache.clear)

    def _case(self, status, reported_at=None, **values):
        case = RescueCase.objects.create(
            title="[QA] Tiêu đề không được đọc vào biểu đồ",
            description="Nội dung riêng của hồ sơ kiểm thử",
            animal_type=RescueCase.AnimalType.CAT,
            status=status, address="Địa chỉ riêng không được thống kê",
            contact_name="Liên hệ riêng", contact_phone="0900000199",
            is_location_private=True, **values,
        )
        if reported_at is not None:
            RescueCase.objects.filter(pk=case.pk).update(reported_at=reported_at)
        return case

    def test_empty_database_renders_two_real_pngs_and_zero_fills_seven_days(self):
        statistics = get_public_rescue_statistics()
        self.assertEqual(statistics["total"], 0)
        self.assertEqual(statistics["rescued_count"], 0)
        self.assertEqual(statistics["daily_average"], 0)
        self.assertEqual(len(statistics["status_rows"]), 3)
        self.assertEqual([row["date"] for row in statistics["daily_rows"]], [
            date(2026, 10, day) for day in range(25, 32)
        ])
        self.assertTrue(all(row["count"] == 0 for row in statistics["daily_rows"]))
        for key in ("status_chart", "daily_chart"):
            self.assertTrue(statistics[key].startswith("data:image/png;base64,"))
            png = base64.b64decode(statistics[key].split(",", 1)[1], validate=True)
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            self.assertGreater(len(png), 1000)
        content = render_to_string("rescue/_public_statistics.html", {"public_statistics": statistics})
        self.assertEqual(content.count('<details class="public-statistics-data">'), 2)
        self.assertEqual(content.count('<table class="public-statistics-table">'), 2)
        self.assertIn('alt="Biểu đồ', content)

    def test_all_received_requests_are_partitioned_into_three_public_count_groups(self):
        for status, _label in RescueCase.Status.choices:
            self._case(status)
        self._case(RescueCase.Status.RESCUED)
        statistics = get_public_rescue_statistics()
        counts = {row["label"]: row["count"] for row in statistics["status_rows"]}
        self.assertNotIn(RescueCase.Status.REPORTED.label, counts)
        self.assertEqual(counts, {"Đã xác nhận": 5, "Đã cứu thành công": 2, "Đã hủy": 2})
        self.assertEqual(statistics["total"], 9)
        self.assertEqual(statistics["rescued_count"], 2)
        self.assertEqual(sum(row["count"] for row in statistics["daily_rows"]), 9)
        self.assertEqual(statistics["daily_average"], 1.29)

    def test_completion_report_is_separate_from_success_until_admin_approval(self):
        rescue_case = self._case(RescueCase.Status.VERIFIED)
        users = get_user_model()
        moderator = users.objects.create_user(
            email="statistics-moderator@example.com", password="test-password",
            role=users.Role.MODERATOR,
        )
        admin = users.objects.create_superuser(
            email="statistics-approver@example.com", password="test-password",
        )
        original = get_public_rescue_statistics()
        report_note = "Đã xử lý tại hiện trường, đang chờ admin duyệt kết quả."
        report = rescue_case.change_status(
            RescueCase.Status.PENDING_REVIEW,
            changed_by=moderator, note=report_note,
        )
        self.assertEqual(report.changed_by, moderator)
        self.assertEqual(report.note, report_note)
        self.assertIsNotNone(report.changed_at)
        rescue_case.refresh_from_db()

        pending = get_public_rescue_statistics()
        counts = {row["label"]: row["count"] for row in pending["status_rows"]}
        self.assertEqual(pending["version"], original["version"])
        self.assertEqual(counts["Đã xác nhận"], 1)
        self.assertEqual(len(counts), 3)
        self.assertEqual(pending["total"], 1)
        self.assertEqual(pending["rescued_count"], 0)
        self.assertIsNone(rescue_case.closed_at)
        self.assertEqual(sum(row["count"] for row in pending["daily_rows"]), 1)

        rescue_case.change_status(
            RescueCase.Status.RESCUED, changed_by=admin,
            note="Admin đã kiểm tra và duyệt thành công.",
        )

        approved = get_public_rescue_statistics()
        counts = {row["label"]: row["count"] for row in approved["status_rows"]}
        self.assertNotEqual(approved["version"], pending["version"])
        self.assertEqual(counts["Đã xác nhận"], 0)
        self.assertEqual(counts[RescueCase.Status.RESCUED.label], 1)
        self.assertEqual(approved["total"], 1)
        self.assertEqual(approved["rescued_count"], 1)
        self.assertIsNotNone(rescue_case.closed_at)
        self.assertEqual(sum(row["count"] for row in approved["daily_rows"]), 1)

    def test_day_boundaries_follow_site_timezone_and_include_empty_days(self):
        self._case(RescueCase.Status.VERIFIED,
                   datetime(2026, 10, 24, 17, tzinfo=datetime_timezone.utc))
        self._case(RescueCase.Status.RESCUED,
                   datetime(2026, 10, 30, 18, tzinfo=datetime_timezone.utc))
        self._case(RescueCase.Status.VERIFIED,
                   datetime(2026, 10, 24, 16, 59, tzinfo=datetime_timezone.utc))
        self._case(RescueCase.Status.VERIFIED,
                   datetime(2026, 10, 31, 17, tzinfo=datetime_timezone.utc))
        with timezone.override("America/Los_Angeles"):
            statistics = get_public_rescue_statistics()
        self.assertEqual([row["count"] for row in statistics["daily_rows"]], [1, 0, 0, 0, 0, 0, 1])
        self.assertEqual(statistics["daily_average"], 0.29)
        self.assertEqual(statistics["window_label"], "25/10/2026 – 31/10/2026")
        self.assertEqual(statistics["total"], 4)

    def test_queries_only_aggregate_status_and_date_without_private_fields(self):
        self._case(RescueCase.Status.VERIFIED)
        with CaptureQueriesContext(connection) as captured:
            statistics = get_public_rescue_statistics()
        case_queries = [item["sql"] for item in captured.captured_queries if "rescue_rescuecase" in item["sql"]]
        self.assertEqual(len(case_queries), 1)
        for sql in case_queries:
            for field in ("title", "description", "contact_name", "contact_phone", "address", "latitude", "longitude", "reporter_id"):
                self.assertNotIn(f'"{field}"', sql)
        content = render_to_string("rescue/_public_statistics.html", {"public_statistics": statistics})
        for private_value in ("Tiêu đề không được đọc", "Địa chỉ riêng", "Liên hệ riêng", "0900000199"):
            self.assertNotIn(private_value, content)

    def test_unchanged_aggregates_reuse_pngs_and_changed_counts_refresh_them(self):
        with patch("rescue.statistics._status_chart", return_value="status-png") as status_chart, \
             patch("rescue.statistics._daily_chart", return_value="daily-png") as daily_chart:
            received = self._case(RescueCase.Status.REPORTED)
            first = get_public_rescue_statistics()
            RescueCase.objects.filter(pk=received.pk).update(status=RescueCase.Status.VERIFIED)
            second = get_public_rescue_statistics()
            self.assertEqual(first, second)
            status_chart.assert_called_once()
            daily_chart.assert_called_once()
            self._case(RescueCase.Status.RESCUED)
            refreshed = get_public_rescue_statistics()
            self.assertEqual(refreshed["total"], 2)
            self.assertEqual(status_chart.call_count, 2)
            self.assertEqual(daily_chart.call_count, 2)

    def test_live_endpoint_exposes_only_public_aggregates_for_guests_members_and_admins(self):
        self._case(RescueCase.Status.VERIFIED)
        self._case(RescueCase.Status.REPORTED)
        users = get_user_model()
        member = users.objects.create_user(
            email="statistics-member@example.com", password="test-password",
        )
        admin = users.objects.create_superuser(
            email="statistics-admin@example.com", password="test-password",
        )
        previous = None
        for user in (None, member, admin):
            with self.subTest(role=user.email if user else "guest"):
                if user is None:
                    self.client.logout()
                else:
                    self.client.force_login(user)
                response = self.client.get(
                    reverse("rescue:public-statistics-live"),
                    {"include_pending": "1", "user_id": admin.pk},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/json")
                data = response.json()
                self.assertEqual(set(data), {
                    "version", "checked_at", "time_zone", "total", "rescued_count",
                    "daily_average", "window_label", "status_chart", "daily_chart",
                    "status_rows", "daily_rows",
                })
                self.assertEqual(data["total"], 2)
                self.assertEqual([row["label"] for row in data["status_rows"]], [
                    "Đã xác nhận", "Đã cứu thành công", "Đã hủy",
                ])
                self.assertEqual(data["rescued_count"], 0)
                self.assertEqual(data["time_zone"], "Asia/Ho_Chi_Minh")
                self.assertEqual(response["ETag"], f'"{data["version"]}"')
                self.assertEqual(response["X-Statistics-Checked-At"], data["checked_at"])
                self.assertIsNotNone(datetime.fromisoformat(data["checked_at"]).utcoffset())
                for row in data["status_rows"]:
                    self.assertEqual(set(row), {"label", "count"})
                    self.assertNotEqual(row["label"], RescueCase.Status.REPORTED.label)
                for row in data["daily_rows"]:
                    self.assertEqual(set(row), {"date", "count"})
                    date.fromisoformat(row["date"])
                for key in ("status_chart", "daily_chart"):
                    self.assertTrue(data[key].startswith("data:image/png;base64,"))
                    png = base64.b64decode(data[key].split(",", 1)[1], validate=True)
                    self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
                text = str(data)
                for private_value in (
                    "Tiêu đề không được đọc", "Nội dung riêng", "Địa chỉ riêng",
                    "Liên hệ riêng", "0900000199", member.email, admin.email,
                ):
                    self.assertNotIn(private_value, text)
                if previous is not None:
                    self.assertEqual(data, previous)
                previous = data

    def test_live_endpoint_returns_304_for_private_edits_and_refreshes_for_new_receipts(self):
        public_case = self._case(RescueCase.Status.VERIFIED)
        pending = self._case(RescueCase.Status.REPORTED)
        url = reverse("rescue:public-statistics-live")
        first = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        etag = first["ETag"]
        RescueCase.objects.filter(pk=public_case.pk).update(
            title="Đổi tiêu đề hồ sơ công khai không đổi số liệu",
            contact_phone="0900000200",
            status=RescueCase.Status.ASSIGNED,
        )
        RescueCase.objects.filter(pk=pending.pk).update(
            title="Đổi tin chưa xác nhận", urgency=RescueCase.Urgency.CRITICAL,
        )

        checked_at = self.now + timedelta(seconds=5)
        with patch("rescue.statistics.timezone.now", return_value=checked_at):
            response = self.client.get(url, HTTP_IF_NONE_MATCH=etag)

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["ETag"], etag)
        self.assertIn("no-store", response["Cache-Control"])
        actual = datetime.fromisoformat(response["X-Statistics-Checked-At"])
        self.assertEqual(actual, checked_at)
        self.assertNotEqual(response["X-Statistics-Checked-At"], first["X-Statistics-Checked-At"])
        self._case(RescueCase.Status.REPORTED)
        refreshed = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.json()["total"], 3)
        self.assertEqual(refreshed.json()["status_rows"][0]["count"], 3)

    def test_live_endpoint_refreshes_after_public_status_changes_and_deletion(self):
        case = self._case(RescueCase.Status.VERIFIED)
        url = reverse("rescue:public-statistics-live")
        first = self.client.get(url)
        etag = first["ETag"]
        RescueCase.objects.filter(pk=case.pk).update(status=RescueCase.Status.ASSIGNED)
        unchanged = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(unchanged.status_code, 304)
        RescueCase.objects.filter(pk=case.pk).update(status=RescueCase.Status.RESCUED)
        response = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response["ETag"], etag)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["status_rows"], [
            {"label": "Đã xác nhận", "count": 0},
            {"label": "Đã cứu thành công", "count": 1},
            {"label": "Đã hủy", "count": 0},
        ])
        self.assertEqual(data["rescued_count"], 1)
        etag = response["ETag"]

        case.delete()
        response = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response["ETag"], etag)
        self.assertEqual(response.json()["total"], 0)
        self.assertEqual(response.json()["rescued_count"], 0)
        self.assertTrue(all(row["count"] == 0 for row in response.json()["daily_rows"]))

    def test_live_endpoint_changes_version_when_site_midnight_moves_the_seven_day_window(self):
        self._case(
            RescueCase.Status.VERIFIED,
            datetime(2026, 10, 24, 17, tzinfo=datetime_timezone.utc),
        )
        url = reverse("rescue:public-statistics-live")
        before = datetime(2026, 10, 31, 16, 59, tzinfo=datetime_timezone.utc)
        after = datetime(2026, 10, 31, 17, tzinfo=datetime_timezone.utc)
        with patch("rescue.statistics.timezone.now", return_value=before):
            first = self.client.get(url)
        with patch("rescue.statistics.timezone.now", return_value=after):
            response = self.client.get(url, HTTP_IF_NONE_MATCH=first["ETag"])

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response["ETag"], first["ETag"])
        self.assertEqual(first.json()["daily_rows"][0], {"date": "2026-10-25", "count": 1})
        self.assertEqual(response.json()["daily_rows"][0], {"date": "2026-10-26", "count": 0})
        self.assertEqual(response.json()["daily_rows"][-1]["date"], "2026-11-01")
        self.assertEqual(response.json()["total"], first.json()["total"])
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(sum(row["count"] for row in response.json()["daily_rows"]), 0)
        self.assertNotEqual(response.json()["window_label"], first.json()["window_label"])

        with patch("rescue.statistics.timezone.now", return_value=after):
            self._case(RescueCase.Status.VERIFIED)
            updated = self.client.get(url, HTTP_IF_NONE_MATCH=response["ETag"])
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["daily_rows"][-1], {"date": "2026-11-01", "count": 1})
        self.assertEqual(updated.json()["total"], 2)

    def test_live_endpoint_is_read_only_uncached_and_does_not_grant_cross_origin_access(self):
        url = reverse("rescue:public-statistics-live")
        response = self.client.get(url, HTTP_ORIGIN="https://untrusted.example")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("Access-Control-Allow-Origin", response)
        self.assertNotIn("Access-Control-Allow-Credentials", response)
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                rejected = getattr(self.client, method)(url, data={})
                self.assertEqual(rejected.status_code, 405)
                self.assertEqual(rejected["Allow"], "GET")

    def test_homepage_connects_existing_charts_to_the_public_five_second_feed(self):
        response = self.client.get(reverse("rescue:case-list"))
        self.assertEqual(response.status_code, 200)
        statistics = response.context["public_statistics"]
        self.assertContains(response, 'id="public-statistics"')
        self.assertContains(response, "data-public-statistics")
        self.assertContains(response, f'data-url="{reverse("rescue:public-statistics-live")}"')
        self.assertContains(response, 'data-poll-interval="5000"')
        self.assertContains(response, f'data-version="{statistics["version"]}"')
        self.assertContains(response, f'data-time-zone="{statistics["time_zone"]}"')
        self.assertContains(response, "/static/js/public-statistics.js")
        self.assertContains(response, 'src="data:image/png;base64,', count=2)
        self.assertContains(response, 'class="public-statistics-table"', count=2)
