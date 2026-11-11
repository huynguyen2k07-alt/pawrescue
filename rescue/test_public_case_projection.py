"""Bản xem công khai và tìm kiếm không tiết lộ hồ sơ hoặc liên hệ riêng."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from organizations.models import RescueOrganization

from .models import RescueAssignment, RescueCase, RescueCaseImage
from .privacy import (
    can_view_case_details,
    can_view_case_internal,
    filter_case_search,
    present_case,
)


class PublicCaseProjectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="projection-admin@example.com", password="test-password", full_name="Admin chính",
        )
        cls.reporter = users.objects.create_user(
            email="projection-reporter@example.com", password="test-password", full_name="Người báo riêng",
        )
        cls.helper = users.objects.create_user(
            email="projection-helper@example.com", password="test-password", full_name="Cộng tác viên",
            role=users.Role.MODERATOR,
        )
        cls.other_user = users.objects.create_user(
            email="projection-other@example.com", password="test-password", full_name="Người ngoài",
        )
        cls.support = users.objects.create_user(
            email="projection-support@example.com", password="test-password", full_name="Nhân viên hỗ trợ",
            role=users.Role.COLLABORATOR,
        )
        cls.organization = RescueOrganization.objects.create(
            name="Tên trung tâm công khai", created_by=cls.admin,
            email="projection-private-center@example.com", phone="0901111222", address="Văn phòng nội bộ",
        )
        cls.case = RescueCase.objects.create(
            title="secret-title-token-unique", description="secret-description-token-unique",
            animal_details="secret-animal-token-unique", animal_type=RescueCase.AnimalType.CAT,
            address="secret-address-token-unique", reporter=cls.reporter, organization=cls.organization,
            contact_name="secret-contact-name-token", contact_phone="0903333444",
            latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            status=RescueCase.Status.RESCUED, is_location_private=False,
        )
        cls.assignment = RescueAssignment.objects.create(
            rescue_case=cls.case, assignee=cls.helper, assigned_by=cls.admin,
        )
        RescueCaseImage.objects.bulk_create([RescueCaseImage(
            rescue_case=cls.case, image="rescue_cases/private-real-image.png", caption="secret-photo-caption",
        )])

    def search_ids(self, user, query, queryset=None):
        queryset = queryset if queryset is not None else RescueCase.objects.all()
        return list(filter_case_search(queryset, user, query).values_list("pk", flat=True))

    def test_only_admin_reporter_and_current_assignee_receive_original_case(self):
        for user in (self.admin, self.reporter, self.helper):
            with self.subTest(user=user.pk):
                self.assertTrue(can_view_case_details(user, self.case))
                self.assertIs(present_case(user, self.case), self.case)
        for user in (AnonymousUser(), self.other_user, self.support):
            with self.subTest(user=getattr(user, "pk", None)):
                self.assertFalse(can_view_case_details(user, self.case))
                self.assertIsNot(present_case(user, self.case), self.case)

    def test_reporter_is_not_internal_participant_unless_also_assigned(self):
        self.assertTrue(can_view_case_internal(self.admin, self.case))
        self.assertTrue(can_view_case_internal(self.helper, self.case))
        self.assertFalse(can_view_case_internal(self.reporter, self.case))
        RescueAssignment.objects.create(rescue_case=self.case, assignee=self.reporter, assigned_by=self.admin)
        self.assertTrue(can_view_case_internal(self.reporter, self.case))

    def test_public_preview_contains_only_generic_content_and_safe_organization(self):
        preview = present_case(AnonymousUser(), self.case)
        self.assertEqual(preview.title, f"Ca cứu hộ Mèo #{self.case.pk}")
        self.assertEqual(preview.pk, self.case.pk)
        self.assertEqual(preview.get_absolute_url(), reverse("rescue:case-detail", args=(self.case.pk,)))
        self.assertEqual(preview.get_animal_type_display(), "Mèo")
        self.assertEqual(preview.get_status_display(), self.case.get_status_display())
        self.assertEqual(preview.get_urgency_display(), self.case.get_urgency_display())
        self.assertEqual(preview.address, "Khu vực gần đúng tại Đà Nẵng")
        self.assertTrue(preview.is_location_private)
        self.assertIsNone(preview.latitude)
        self.assertIsNone(preview.longitude)
        self.assertIsNone(preview.reporter)
        self.assertIsNone(preview.reporter_id)
        self.assertEqual(preview.contact_name, "")
        self.assertEqual(preview.contact_phone, "")
        self.assertEqual(preview.animal_details, "")
        self.assertFalse(preview.images.all())
        self.assertEqual(preview.organization.name, self.organization.name)
        self.assertEqual(preview.organization.phone, "")
        self.assertEqual(preview.organization.email, "")
        self.assertEqual(preview.organization.address, "")
        self.assertFalse(hasattr(preview, "assignments"))
        self.assertFalse(hasattr(preview, "updates"))
        self.assertFalse(hasattr(preview, "status_history"))
        self.assertNotIn("secret-", repr(preview))
        self.assertNotIn(self.reporter.email, repr(preview))

    def test_public_projection_does_not_change_model_contact_or_location(self):
        present_case(self.other_user, self.case)
        self.case.refresh_from_db()
        self.assertEqual(self.case.title, "secret-title-token-unique")
        self.assertEqual(self.case.contact_phone, "0903333444")
        self.assertEqual(self.case.latitude, Decimal("16.054407"))
        self.assertFalse(self.case.is_location_private)
        self.assertEqual(self.case.images.count(), 1)

    def test_inactive_and_revoked_participants_lose_details_internal_and_raw_search(self):
        self.assignment.is_active = False
        self.assignment.save(update_fields=("is_active",))
        self.assertFalse(can_view_case_details(self.helper, self.case))
        self.assertFalse(can_view_case_internal(self.helper, self.case))
        self.assertEqual(self.search_ids(self.helper, self.case.address), [])
        self.reporter.is_active = False
        self.reporter.save(update_fields=("is_active",))
        self.assertFalse(can_view_case_details(self.reporter, self.case))
        self.assertEqual(self.search_ids(self.reporter, self.case.title), [])
        self.admin.is_active = False
        self.admin.save(update_fields=("is_active",))
        self.assertFalse(can_view_case_details(self.admin, self.case))
        self.assertFalse(can_view_case_internal(self.admin, self.case))
        self.assertEqual(self.search_ids(self.admin, self.case.address), [])

    def test_prefetched_assignments_avoid_additional_permission_queries(self):
        case = RescueCase.objects.select_related("organization").prefetch_related("assignments").get(pk=self.case.pk)
        with self.assertNumQueries(0):
            self.assertTrue(can_view_case_details(self.helper, case))
            self.assertTrue(can_view_case_internal(self.helper, case))
            self.assertIs(present_case(self.helper, case), case)
            self.assertFalse(can_view_case_details(self.other_user, case))
            self.assertIsNot(present_case(self.other_user, case), case)

    def test_public_search_uses_safe_animal_status_id_and_generated_title(self):
        for query in ("mèo", "ĐÃ CỨU THÀNH CÔNG", str(self.case.pk), f"#{self.case.pk}",
                      f"Ca cứu hộ Mèo #{self.case.pk}", "Ca cứu hộ"):
            with self.subTest(query=query):
                self.assertEqual(self.search_ids(AnonymousUser(), query), [self.case.pk])

    def test_search_cannot_reveal_hidden_title_description_or_address_to_other_users(self):
        for user in (AnonymousUser(), self.other_user, self.support):
            for query in (self.case.title, self.case.description, self.case.address,
                          self.case.animal_details, self.case.contact_name, self.case.contact_phone):
                with self.subTest(user=getattr(user, "pk", None), query=query):
                    self.assertEqual(self.search_ids(user, query), [])

    def test_search_permits_raw_fields_only_on_users_own_or_assigned_records(self):
        other_case = RescueCase.objects.create(
            title=self.case.title, description=self.case.description, address=self.case.address,
            animal_type=RescueCase.AnimalType.DOG, reporter=self.other_user,
        )
        for user in (self.reporter, self.helper):
            for query in (self.case.title, self.case.description, self.case.address):
                with self.subTest(user=user.pk, query=query):
                    self.assertEqual(self.search_ids(user, query), [self.case.pk])
        self.assertEqual(set(self.search_ids(self.admin, self.case.address)), {self.case.pk, other_case.pk})
        self.assertEqual(self.search_ids(self.other_user, self.case.address), [other_case.pk])

    def test_search_preserves_existing_queryset_scope_and_handles_large_numeric_input(self):
        scoped = RescueCase.objects.exclude(pk=self.case.pk)
        self.assertEqual(self.search_ids(self.admin, self.case.title, scoped), [])
        self.assertEqual(self.search_ids(AnonymousUser(), "9" * 150), [])
        self.assertEqual(self.search_ids(AnonymousUser(), " "), [self.case.pk])
