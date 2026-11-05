from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    CaseStatusHistory,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseMessage,
    RescueUpdate,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminAndGuestJourneyTests(TestCase):
    """Kiểm thử hành trình báo tin, tiếp nhận, phân công và đánh giá kết quả cuối cùng."""

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.admin = user_model.objects.create_superuser(
            email="journey-admin@example.com",
            password="test-password",
            full_name="Journey Admin",
        )
        cls.guest = user_model.objects.create_user(
            email="journey-guest@example.com",
            password="test-password",
            full_name="Journey Guest",
            phone="0901234567",
        )
        cls.collaborator = user_model.objects.create_user(
            email="journey-collaborator@example.com",
            password="test-password",
            full_name="Journey Collaborator",
            role=user_model.Role.COLLABORATOR,
        )

    def test_report_dispatch_private_exchange_field_report_and_admin_closure(self):
        self.client.force_login(self.guest)
        report_response = self.client.post(
            reverse("rescue:case-create"),
            {
                "title": "Chó bị thương cần hỗ trợ",
                "animal_type": RescueCase.AnimalType.DOG,
                "animal_details": "Lông vàng, đeo vòng cổ xanh",
                "urgency": RescueCase.Urgency.HIGH,
                "description": "Chó bị đau chân và đang nằm bên đường.",
                "address": "Hải Châu, Đà Nẵng",
                "latitude": "16.054407",
                "longitude": "108.202167",
                "location_confirmed": "on",
                "contact_name": self.guest.full_name,
                "contact_phone": self.guest.phone,
            },
        )
        rescue_case = RescueCase.objects.get(reporter=self.guest)
        detail_url = reverse("rescue:case-detail", args=(rescue_case.pk,))
        messages_url = reverse("rescue:case-messages", args=(rescue_case.pk,))
        status_url = reverse("rescue:case-update-status", args=(rescue_case.pk,))
        self.assertRedirects(report_response, detail_url)
        self.assertEqual(rescue_case.status, RescueCase.Status.REPORTED)
        self.assertEqual(rescue_case.latitude, Decimal("16.054407"))
        self.assertEqual(rescue_case.longitude, Decimal("108.202167"))
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.admin,
                rescue_case=rescue_case,
                kind=Notification.Kind.CASE_REPORTED,
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.collaborator,
                rescue_case=rescue_case,
            ).exists()
        )

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("admin:index")), rescue_case.title)
        assignment_note = "Đến địa chỉ hiện trường, mang lồng vận chuyển."
        assignment_response = self.client.post(
            reverse("rescue:case-assign", args=(rescue_case.pk,)),
            {"assignee": self.collaborator.pk, "notes": assignment_note},
        )
        self.assertRedirects(assignment_response, detail_url)
        assignment = RescueAssignment.objects.get(
            rescue_case=rescue_case, assignee=self.collaborator
        )
        self.assertEqual(assignment.assigned_by, self.admin)
        self.assertEqual(assignment.notes, assignment_note)
        rescue_case.refresh_from_db()
        self.assertEqual(rescue_case.status, RescueCase.Status.ASSIGNED)
        self.assertTrue(
            RescueCaseMessage.objects.filter(
                rescue_case=rescue_case,
                sender=self.admin,
                recipient=self.collaborator,
                body__contains=assignment_note,
            ).exists()
        )

        admin_message = "Gọi bác sĩ thú y trước khi đưa động vật tới."
        self.assertRedirects(
            self.client.post(
                messages_url,
                {"recipient": self.collaborator.pk, "body": admin_message},
            ),
            messages_url,
        )
        self.client.force_login(self.collaborator)
        self.assertContains(self.client.get(messages_url), admin_message)
        self.assertTrue(
            RescueCaseMessage.objects.filter(
                body=admin_message, read_at__isnull=False
            ).exists()
        )
        collaborator_reply = "Đã liên hệ bác sĩ và đang đến hiện trường."
        self.assertRedirects(
            self.client.post(
                messages_url,
                {"recipient": self.admin.pk, "body": collaborator_reply},
            ),
            messages_url,
        )
        self.assertTrue(
            RescueCaseMessage.objects.filter(
                rescue_case=rescue_case,
                sender=self.collaborator,
                recipient=self.admin,
                body=collaborator_reply,
            ).exists()
        )
        self.assertEqual(
            self.client.post(
                status_url,
                {"status": RescueCase.Status.CLOSED, "note": "Tự chốt ca."},
            ).status_code,
            403,
        )

        field_note = "Đã sơ cứu và bàn giao động vật cho bác sĩ thú y."
        self.assertRedirects(
            self.client.post(
                reverse("rescue:case-add-update", args=(rescue_case.pk,)),
                {"note": field_note},
            ),
            detail_url,
        )
        self.assertTrue(
            RescueUpdate.objects.filter(
                rescue_case=rescue_case,
                author=self.collaborator,
                note=field_note,
            ).exists()
        )

        self.client.force_login(self.guest)
        reporter_detail = self.client.get(detail_url)
        self.assertNotContains(reporter_detail, assignment_note)
        self.assertNotContains(reporter_detail, admin_message)
        self.assertNotContains(reporter_detail, collaborator_reply)
        self.assertEqual(self.client.get(messages_url).status_code, 404)

        self.client.force_login(self.admin)
        self.assertContains(self.client.get(messages_url), collaborator_reply)
        self.assertContains(self.client.get(detail_url), field_note)
        self.assertRedirects(
            self.client.post(status_url, {"status": RescueCase.Status.RESCUED}),
            detail_url,
        )
        rescue_case.refresh_from_db()
        self.assertEqual(rescue_case.status, RescueCase.Status.ASSIGNED)
        self.assertIsNone(rescue_case.closed_at)

        assessment = "Đã kiểm tra báo cáo và xác nhận bàn giao an toàn. Hoàn tất ca cứu hộ."
        self.assertRedirects(
            self.client.post(
                status_url,
                {"status": RescueCase.Status.RESCUED, "note": assessment},
            ),
            detail_url,
        )
        rescue_case.refresh_from_db()
        self.assertEqual(rescue_case.status, RescueCase.Status.RESCUED)
        self.assertIsNotNone(rescue_case.closed_at)
        self.assertTrue(
            CaseStatusHistory.objects.filter(
                rescue_case=rescue_case,
                changed_by=self.admin,
                to_status=RescueCase.Status.RESCUED,
                note=assessment,
            ).exists()
        )

        self.client.force_login(self.guest)
        self.assertContains(self.client.get(detail_url), assessment)
        self.assertContains(
            self.client.get(reverse("rescue:notification-list")),
            "Trạng thái ca cứu hộ đã thay đổi",
        )
