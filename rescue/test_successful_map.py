"""Kiểm tra bản đồ tổng chỉ chứa ca cứu thành công và vẫn bảo vệ vị trí riêng tư."""

import json
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from organizations.models import OrganizationMembership, RescueOrganization

from .models import (
    CaseStatusHistory,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseImage,
)


class SuccessfulRescueMapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="successful-map-admin@example.com", password="test-password",
        )
        cls.reporter = users.objects.create_user(
            email="successful-map-reporter@example.com", password="test-password",
        )
        cls.assignee = users.objects.create_user(
            email="successful-map-assignee@example.com", password="test-password",
            role=users.Role.COLLABORATOR,
        )
        cls.other_operator = users.objects.create_user(
            email="successful-map-other-operator@example.com", password="test-password",
            role=users.Role.COLLABORATOR,
        )
        cls.member = users.objects.create_user(
            email="successful-map-member@example.com", password="test-password",
        )
        cls.staff = users.objects.create_user(
            email="successful-map-staff@example.com", password="test-password", is_staff=True,
        )
        cls.manager = users.objects.create_user(
            email="successful-map-manager@example.com", password="test-password",
        )
        organization = RescueOrganization.objects.create(
            name="Đơn vị kiểm thử bản đồ thành công", is_verified=True,
        )
        OrganizationMembership.objects.create(
            organization=organization, user=cls.manager,
            role=OrganizationMembership.Role.MANAGER,
        )
        cls.cases = {}
        cls.images = {}
        for index, status in enumerate(RescueCase.Status.values):
            case = RescueCase.objects.create(
                title=f"[QA-MAP] Hồ sơ riêng {status}",
                description=f"Nội dung kiểm thử trạng thái {status}.",
                animal_type=RescueCase.AnimalType.CAT,
                status=status, reporter=cls.reporter, organization=organization,
                address=f"Địa chỉ riêng kiểm thử {status}, Đà Nẵng",
                latitude=Decimal("16.051101") + Decimal("0.001001") * index,
                longitude=Decimal("108.201201") + Decimal("0.001001") * index,
                is_location_private=True,
            )
            cls.cases[status] = case
            cls.images[status] = RescueCaseImage.objects.create(
                rescue_case=case, image=f"fixtures/successful-map-{status}.png",
            )
            RescueAssignment.objects.create(
                rescue_case=case, assignee=cls.assignee, assigned_by=cls.admin,
            )
        cls.public_case = RescueCase.objects.create(
            title="[QA-MAP] Ca đã cứu với vị trí công khai",
            description="Đã hoàn thành cứu hộ.", animal_type=RescueCase.AnimalType.DOG,
            status=RescueCase.Status.RESCUED, reporter=cls.reporter,
            address="Điểm cứu hộ công khai, Đà Nẵng",
            latitude=Decimal("16.092224"), longitude=Decimal("108.222337"),
        )

    def _map(self, user=None, query=None):
        if user is None:
            self.client.logout()
        else:
            self.client.force_login(user)
        return self.client.get(reverse("rescue:case-map"), query or {})

    def _embedded_cases(self, response):
        script = re.search(
            r'<script id="map-case-data" type="application/json">(.*?)</script>',
            response.content.decode(), re.DOTALL,
        )
        self.assertIsNotNone(script)
        return json.loads(script.group(1))

    def test_marker_details_include_completion_time_and_organization_without_private_content(self):
        case = self.cases[RescueCase.Status.RESCUED]
        completed_at = timezone.now()
        RescueCase.objects.filter(pk=case.pk).update(closed_at=completed_at, contact_phone="0901122334")
        response = self._map()
        marker = next(item for item in self._embedded_cases(response) if item["id"] == case.pk)
        self.assertEqual(marker["completed_at_display"], timezone.localtime(completed_at).strftime("%H:%M, %d/%m/%Y"))
        self.assertEqual(marker["organization"], case.organization.name)
        self.assertEqual(marker["detail_url"], reverse("rescue:case-detail", args=(case.pk,)))
        self.assertEqual(marker["image_url"], reverse("rescue:case-image", args=(self.images[case.status].pk,)))
        self.assertNotIn("description", marker)
        self.assertNotIn("contact_phone", marker)
        self.assertNotContains(response, "0901122334")
        self.assertNotContains(response, case.address)
        self.assertNotContains(response, "Google Maps ↗")
        detail = self.client.get(marker["detail_url"])
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, case.title)
        self.assertNotContains(detail, case.address)

    def test_legacy_success_without_a_completion_date_does_not_invent_one(self):
        response = self._map()
        marker = next(item for item in self._embedded_cases(response) if item["id"] == self.public_case.pk)
        self.assertEqual(marker["completed_at_display"], "")

    def test_all_roles_only_receive_successful_cases_in_cards_and_embedded_json(self):
        private_success = self.cases[RescueCase.Status.RESCUED]
        expected_ids = {private_success.pk, self.public_case.pk}
        roles = (
            None, self.member, self.reporter, self.assignee, self.other_operator,
            self.staff, self.manager, self.admin,
        )
        queries = (
            {},
            {"status": "reported", "include_pending": "1"},
            {"status": "all", "show_all": "1", "include_active": "1"},
        )
        for user in roles:
            for query in queries:
                with self.subTest(user=user.email if user else "guest", query=query):
                    response = self._map(user, query)
                    self.assertEqual(response.status_code, 200)
                    markers = response.context["map_cases"]
                    self.assertEqual({item["id"] for item in markers}, expected_ids)
                    self.assertTrue(all(
                        item["status_value"] == RescueCase.Status.RESCUED
                        for item in markers
                    ))
                    self.assertEqual(self._embedded_cases(response), markers)
                    card_ids = re.findall(r'data-case-id="(\d+)"', response.content.decode())
                    self.assertEqual({int(value) for value in card_ids}, expected_ids)
                    self.assertEqual(len(card_ids), len(expected_ids))
                    for status, case in self.cases.items():
                        if status == RescueCase.Status.RESCUED:
                            continue
                        self.assertNotContains(response, case.title)
                        self.assertNotContains(response, case.address)
                        self.assertNotContains(response, str(float(case.latitude)))
                        self.assertNotContains(response, str(float(case.longitude)))
                        self.assertNotContains(
                            response, reverse("rescue:case-image", args=(self.images[status].pk,)),
                        )
                    marker = next(item for item in markers if item["id"] == private_success.pk)
                    can_view_exact = user in (self.admin, self.reporter, self.assignee)
                    self.assertEqual(marker["is_approximate"], not can_view_exact)
                    if can_view_exact:
                        self.assertEqual(marker["latitude"], float(private_success.latitude))
                        self.assertEqual(marker["longitude"], float(private_success.longitude))
                        self.assertEqual(marker["address"], private_success.address)
                    else:
                        self.assertEqual(marker["latitude"], round(float(private_success.latitude), 2))
                        self.assertEqual(marker["longitude"], round(float(private_success.longitude), 2))
                        self.assertNotContains(response, private_success.address)
                        self.assertNotContains(response, str(float(private_success.latitude)))
                        self.assertNotContains(response, str(float(private_success.longitude)))
                    public_marker = next(item for item in markers if item["id"] == self.public_case.pk)
                    self.assertFalse(public_marker["is_approximate"])
                    self.assertEqual(public_marker["latitude"], float(self.public_case.latitude))
                    self.assertEqual(public_marker["longitude"], float(self.public_case.longitude))

    def test_empty_successful_map_does_not_fall_back_to_active_cases_or_write_records(self):
        RescueCase.objects.filter(status=RescueCase.Status.RESCUED).update(latitude=None)
        before_statuses = list(RescueCase.objects.order_by("pk").values_list("pk", "status"))
        before_assignments = RescueAssignment.objects.count()
        for user in (None, self.reporter, self.assignee, self.admin):
            with self.subTest(user=user.email if user else "guest"):
                response = self._map(user, {"status": "assigned"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["map_cases"], [])
                self.assertEqual(self._embedded_cases(response), [])
                self.assertContains(response, "data-cases-map")
                self.assertNotContains(response, "data-case-id=")
        self.assertEqual(
            list(RescueCase.objects.order_by("pk").values_list("pk", "status")),
            before_statuses,
        )
        self.assertEqual(RescueAssignment.objects.count(), before_assignments)
        self.assertFalse(CaseStatusHistory.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_authorized_people_keep_exact_active_case_maps_inside_case_details(self):
        active_statuses = (
            RescueCase.Status.REPORTED, RescueCase.Status.VERIFIED,
            RescueCase.Status.ASSIGNED, RescueCase.Status.IN_PROGRESS,
        )
        for status in active_statuses:
            case = self.cases[status]
            for user in (self.admin, self.reporter, self.assignee):
                with self.subTest(status=status, user=user.email):
                    self.client.force_login(user)
                    response = self.client.get(reverse("rescue:case-detail", args=(case.pk,)))
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context["can_view_location"])
                    self.assertFalse(response.context["map_is_approximate"])
                    self.assertEqual(response.context["map_latitude"], float(case.latitude))
                    self.assertEqual(response.context["map_longitude"], float(case.longitude))
                    self.assertContains(response, "data-case-map")
                    self.assertContains(response, case.address)

    def test_case_only_enters_map_when_rescued_and_leaves_after_other_terminal_status(self):
        case = self.cases[RescueCase.Status.VERIFIED]
        for status in (
            RescueCase.Status.VERIFIED, RescueCase.Status.RESCUED,
            RescueCase.Status.CLOSED, RescueCase.Status.CANCELLED,
        ):
            RescueCase.objects.filter(pk=case.pk).update(status=status)
            with self.subTest(status=status):
                response = self._map(self.admin, {"status": "all"})
                ids = {item["id"] for item in response.context["map_cases"]}
                self.assertEqual(case.pk in ids, status == RescueCase.Status.RESCUED)
