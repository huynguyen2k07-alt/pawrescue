"""Kiểm thử điều phối cứu hộ và tin nhắn riêng theo ca."""

import base64
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from organizations.models import OrganizationMembership, RescueOrganization

from .models import (
    CaseStatusHistory,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseImage,
    RescueCaseMessage,
    RescueUpdate,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class RescueDispatchWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="dispatch-admin@example.com", password="test-password",
            full_name="Dispatch Admin",
        )
        cls.other_admin = users.objects.create_superuser(
            email="dispatch-other-admin@example.com", password="test-password",
            full_name="Other Admin",
        )
        cls.inactive_admin = users.objects.create_superuser(
            email="dispatch-inactive-admin@example.com", password="test-password",
            full_name="Inactive Admin", is_active=False,
        )
        cls.reporter = users.objects.create_user(
            email="dispatch-reporter@example.com", password="test-password",
            full_name="Report Owner", phone="0901234567",
        )
        cls.assignee = users.objects.create_user(
            email="dispatch-assignee@example.com", password="test-password",
            full_name="Assigned Rescuer", role=users.Role.COLLABORATOR,
        )
        cls.other_operator = users.objects.create_user(
            email="dispatch-other-operator@example.com", password="test-password",
            full_name="Other Rescuer", role=users.Role.COLLABORATOR,
        )
        cls.staff = users.objects.create_user(
            email="dispatch-staff@example.com", password="test-password",
            full_name="Ordinary Staff", is_staff=True,
        )
        cls.manager = users.objects.create_user(
            email="dispatch-manager@example.com", password="test-password",
            full_name="Organization Manager",
        )
        cls.organization = RescueOrganization.objects.create(
            name="Dispatch Test Team", created_by=cls.manager, is_verified=True,
        )
        OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.manager,
            role=OrganizationMembership.Role.MANAGER,
        )
        cls.private_case = RescueCase.objects.create(
            title="Private injured cat report",
            description="The animal needs assistance.",
            animal_type=RescueCase.AnimalType.CAT,
            reporter=cls.reporter,
            address="123 Nguyễn Văn Linh, Hải Châu, Đà Nẵng",
            latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            is_location_private=True,
            contact_name=cls.reporter.full_name,
            contact_phone=cls.reporter.phone,
        )

    def assign(self, user=None, case=None):
        return RescueAssignment.objects.create(
            rescue_case=case or self.private_case,
            assignee=user or self.assignee,
            assigned_by=self.admin,
            notes="Private dispatch: bring the recovery carrier.",
        )

    def message_url(self, case=None):
        return reverse("rescue:case-messages", args=((case or self.private_case).pk,))

    def test_assigned_organization_manager_can_open_rescue_workspace(self):
        self.assign(user=self.manager)
        self.client.force_login(self.manager)
        response = self.client.get(reverse("collaborators:dashboard"))
        self.assertContains(response, self.private_case.title)
        self.assertContains(response, "Ca cứu hộ được giao")
        self.assertNotContains(response, 'href="/support/inbox/"')

    def report_payload(self, **changes):
        payload = {
            "title": "New map-pinned report",
            "animal_type": RescueCase.AnimalType.DOG,
            "urgency": RescueCase.Urgency.HIGH,
            "description": "A dog has an injured leg.",
            "address": "456 Trần Phú, Hải Châu, Đà Nẵng",
            "latitude": "16.060500", "longitude": "108.209800",
            "contact_name": self.reporter.full_name,
            "contact_phone": self.reporter.phone,
        }
        payload.update(changes)
        return payload

    def test_new_report_notifies_only_active_admins_and_keeps_map_pin(self):
        self.client.force_login(self.reporter)
        response = self.client.post(
            reverse("rescue:case-create"), self.report_payload(),
        )
        created = RescueCase.objects.get(title="New map-pinned report")
        self.assertRedirects(response, reverse("rescue:case-detail", args=(created.pk,)))
        self.assertEqual(created.reporter, self.reporter)
        self.assertEqual(created.address, self.report_payload()["address"])
        self.assertEqual(created.latitude, Decimal("16.060500"))
        self.assertEqual(created.longitude, Decimal("108.209800"))
        self.assertEqual(
            set(Notification.objects.filter(
                rescue_case=created, kind=Notification.Kind.CASE_REPORTED,
            ).values_list("recipient_id", flat=True)),
            {self.admin.pk, self.other_admin.pk},
        )

    def test_submission_requires_address_and_complete_in_bounds_coordinates(self):
        self.client.force_login(self.reporter)
        initial_count = RescueCase.objects.count()
        invalid_values = (
            {"address": ""}, {"latitude": ""}, {"longitude": ""},
            {"latitude": "", "longitude": ""},
            {"latitude": "10.776900", "longitude": "106.700900"},
        )
        for changes in invalid_values:
            with self.subTest(changes=changes):
                response = self.client.post(
                    reverse("rescue:case-create"), self.report_payload(**changes),
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(RescueCase.objects.count(), initial_count)

    def test_unassigned_collaborator_and_manager_cannot_discover_private_report(self):
        detail_url = reverse("rescue:case-detail", args=(self.private_case.pk,))
        for user in (self.other_operator, self.manager, self.staff):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertEqual(self.client.get(detail_url).status_code, 404)
                self.assertNotContains(
                    self.client.get(reverse("rescue:case-list")), self.private_case.title,
                )
                map_response = self.client.get(reverse("rescue:case-map"))
                self.assertNotIn(
                    self.private_case.pk,
                    [item["id"] for item in map_response.context["map_cases"]],
                )
                dashboard = self.client.get(reverse("collaborators:dashboard"))
                if dashboard.status_code == 200:
                    self.assertNotContains(dashboard, self.private_case.title)

    def test_assigned_rescuer_can_see_exact_private_location_and_contact(self):
        self.assign()
        self.client.force_login(self.assignee)
        detail = self.client.get(reverse("rescue:case-detail", args=(self.private_case.pk,)))
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.context["can_view_contact"])
        self.assertTrue(detail.context["can_view_location"])
        self.assertFalse(detail.context["map_is_approximate"])
        self.assertContains(detail, self.private_case.contact_phone)
        self.assertContains(detail, self.private_case.address)
        marker = next(item for item in self.client.get(
            reverse("rescue:case-map"),
        ).context["map_cases"] if item["id"] == self.private_case.pk)
        self.assertEqual(marker["latitude"], float(self.private_case.latitude))
        self.assertEqual(marker["longitude"], float(self.private_case.longitude))

    def test_private_report_images_require_admin_reporter_or_active_assignment(self):
        with TemporaryDirectory() as media_root, override_settings(
            PRIVATE_RESCUE_MEDIA_ROOT=media_root,
        ):
            image = RescueCaseImage.objects.create(
                rescue_case=self.private_case, uploaded_by=self.reporter,
                image=SimpleUploadedFile("scene.png", PNG_1X1, content_type="image/png"),
            )
            image_url = reverse("rescue:case-image", args=(image.pk,))
            self.assertEqual(self.client.get(image_url).status_code, 404)
            self.client.force_login(self.other_operator)
            self.assertEqual(self.client.get(image_url).status_code, 404)
            assignment = self.assign()
            for user in (self.admin, self.reporter, self.assignee):
                self.client.force_login(user)
                response = self.client.get(image_url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(b"".join(response.streaming_content))
            assignment.is_active = False
            assignment.save(update_fields=("is_active",))
            self.client.force_login(self.assignee)
            self.assertEqual(self.client.get(image_url).status_code, 404)

    def test_verified_case_remains_available_on_public_map(self):
        self.private_case.status = RescueCase.Status.VERIFIED
        self.private_case.save(update_fields=("status",))
        response = self.client.get(reverse("rescue:case-map"))
        marker = next(item for item in response.context["map_cases"]
                      if item["id"] == self.private_case.pk)
        self.assertTrue(marker["is_approximate"])
        self.assertNotEqual(marker["latitude"], float(self.private_case.latitude))
        self.assertNotContains(response, self.private_case.contact_phone)
        self.assertNotContains(response, self.private_case.address)

    def test_only_admin_can_dispatch_and_active_collaborators_or_managers_are_eligible(self):
        dispatch_url = reverse("rescue:case-assign", args=(self.private_case.pk,))
        for user in (self.other_operator, self.manager, self.reporter, self.staff):
            with self.subTest(denied_user=user.email):
                self.client.force_login(user)
                response = self.client.post(dispatch_url, {"assignee": self.assignee.pk})
                self.assertEqual(response.status_code, 403)
        self.assertFalse(self.private_case.assignments.exists())
        self.client.force_login(self.admin)
        for recipient in (self.assignee, self.manager):
            with self.subTest(allowed_recipient=recipient.email):
                self.client.post(dispatch_url, {"assignee": recipient.pk, "notes": "Bring a carrier."})
                self.assertTrue(self.private_case.assignments.filter(
                    assignee=recipient, assigned_by=self.admin, is_active=True,
                ).exists())

    def test_admin_cannot_dispatch_to_ordinary_user_or_inactive_operator(self):
        volunteer = get_user_model().objects.create_user(
            email="dispatch-volunteer@example.com", password="test-password",
            full_name="Organization Volunteer",
        )
        OrganizationMembership.objects.create(
            organization=self.organization, user=volunteer,
            role=OrganizationMembership.Role.VOLUNTEER,
        )
        self.assignee.is_active = False
        self.assignee.save(update_fields=("is_active",))
        self.client.force_login(self.admin)
        for recipient in (self.reporter, self.staff, self.assignee, volunteer):
            with self.subTest(recipient=recipient.email):
                self.client.post(
                    reverse("rescue:case-assign", args=(self.private_case.pk,)),
                    {"assignee": recipient.pk},
                )
                self.assertFalse(self.private_case.assignments.filter(assignee=recipient).exists())

    def test_manager_cannot_self_claim_unassigned_report(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("rescue:case-claim", args=(self.private_case.pk,)),
            {"organization": self.organization.pk},
        )
        self.assertEqual(response.status_code, 403)
        self.private_case.refresh_from_db()
        self.assertIsNone(self.private_case.organization_id)

    def test_assignee_progress_notifies_admins_reporter_and_other_assignees(self):
        self.assign()
        self.assign(user=self.other_operator)
        self.client.force_login(self.assignee)
        response = self.client.post(
            reverse("rescue:case-add-update", args=(self.private_case.pk,)),
            {"note": "The animal is safe; awaiting administrator review."},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RescueUpdate.objects.filter(
            rescue_case=self.private_case, author=self.assignee,
        ).exists())
        self.assertEqual(
            set(Notification.objects.filter(
                rescue_case=self.private_case, kind=Notification.Kind.CASE_UPDATED,
            ).values_list("recipient_id", flat=True)),
            {self.admin.pk, self.other_admin.pk, self.reporter.pk, self.other_operator.pk},
        )

    def test_assignee_and_manager_cannot_set_status_or_close_case(self):
        self.assign()
        self.assign(user=self.manager)
        for user in (self.assignee, self.manager, self.reporter, self.staff):
            for status in (RescueCase.Status.IN_PROGRESS, RescueCase.Status.CLOSED):
                with self.subTest(user=user.email, status=status):
                    self.client.force_login(user)
                    response = self.client.post(
                        reverse("rescue:case-update-status", args=(self.private_case.pk,)),
                        {"status": status, "note": "Attempted final decision."},
                    )
                    self.assertEqual(response.status_code, 403)
        self.private_case.refresh_from_db()
        self.assertEqual(self.private_case.status, RescueCase.Status.REPORTED)
        self.assertFalse(self.private_case.status_history.exists())

    def test_admin_terminal_decision_requires_written_evaluation(self):
        self.client.force_login(self.admin)
        for terminal in (RescueCase.Status.RESCUED, RescueCase.Status.CLOSED, RescueCase.Status.CANCELLED):
            with self.subTest(status=terminal):
                self.client.post(
                    reverse("rescue:case-update-status", args=(self.private_case.pk,)),
                    {"status": terminal, "note": "   "},
                )
                self.private_case.refresh_from_db()
                self.assertEqual(self.private_case.status, RescueCase.Status.REPORTED)
                self.assertIsNone(self.private_case.closed_at)
                self.assertFalse(self.private_case.status_history.exists())
        evaluation = "Reviewed the field report and photos; rescue confirmed complete."
        self.client.post(
            reverse("rescue:case-update-status", args=(self.private_case.pk,)),
            {"status": RescueCase.Status.CLOSED, "note": evaluation},
        )
        self.private_case.refresh_from_db()
        self.assertEqual(self.private_case.status, RescueCase.Status.CLOSED)
        self.assertIsNotNone(self.private_case.closed_at)
        history = CaseStatusHistory.objects.get(rescue_case=self.private_case)
        self.assertEqual(history.changed_by, self.admin)
        self.assertEqual(history.note, evaluation)

    def test_finalized_case_rejects_reopening_assignment_and_field_updates(self):
        self.assign()
        self.private_case.change_status(
            RescueCase.Status.CLOSED, changed_by=self.admin, note="Final review complete.",
        )
        self.client.force_login(self.admin)
        self.client.post(
            reverse("rescue:case-update-status", args=(self.private_case.pk,)),
            {"status": RescueCase.Status.IN_PROGRESS, "note": "Try to reopen."},
        )
        self.client.post(
            reverse("rescue:case-assign", args=(self.private_case.pk,)),
            {"assignee": self.other_operator.pk},
        )
        self.client.force_login(self.assignee)
        self.client.post(
            reverse("rescue:case-add-update", args=(self.private_case.pk,)),
            {"note": "A late field update."},
        )
        self.private_case.refresh_from_db()
        self.assertEqual(self.private_case.status, RescueCase.Status.CLOSED)
        self.assertEqual(self.private_case.status_history.count(), 1)
        self.assertFalse(self.private_case.assignments.filter(assignee=self.other_operator).exists())
        self.assertFalse(self.private_case.updates.exists())

    def test_admin_quick_terminal_action_cannot_bypass_written_evaluation(self):
        self.client.force_login(self.admin)
        for terminal in (RescueCase.Status.RESCUED, RescueCase.Status.CLOSED, RescueCase.Status.CANCELLED):
            with self.subTest(status=terminal):
                self.client.post(reverse(
                    "admin:rescue_rescuecase_quick_status",
                    args=(self.private_case.pk, terminal),
                ))
                self.private_case.refresh_from_db()
                self.assertEqual(self.private_case.status, RescueCase.Status.REPORTED)
                self.assertIsNone(self.private_case.closed_at)
                self.assertFalse(self.private_case.status_history.exists())

    def test_admin_can_message_assignee_and_assignee_can_reply_privately(self):
        self.assign()
        self.client.force_login(self.admin)
        self.client.post(self.message_url(), {
            "recipient": self.assignee.pk, "body": "Private instruction: use the side entrance.",
        })
        instruction = RescueCaseMessage.objects.get(
            rescue_case=self.private_case, sender=self.admin, recipient=self.assignee,
        )
        self.assertIsNone(instruction.read_at)
        self.assertEqual(Notification.objects.get(
            rescue_case=self.private_case, kind=Notification.Kind.CASE_MESSAGE,
        ).recipient, self.assignee)
        self.client.force_login(self.assignee)
        self.assertEqual(self.client.get(self.message_url()).status_code, 200)
        instruction.refresh_from_db()
        self.assertIsNotNone(instruction.read_at)
        self.client.post(self.message_url(), {
            "recipient": self.admin.pk, "body": "Private reply: team has arrived.",
        })
        self.assertTrue(RescueCaseMessage.objects.filter(
            rescue_case=self.private_case, sender=self.assignee, recipient=self.admin,
            body="Private reply: team has arrived.",
        ).exists())
        self.client.force_login(self.reporter)
        detail = self.client.get(reverse("rescue:case-detail", args=(self.private_case.pk,)))
        self.assertNotContains(detail, instruction.body)

    def test_message_endpoint_rejects_reporter_and_unassigned_operator(self):
        self.assign()
        for user in (self.reporter, self.other_operator, self.manager, self.staff):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertIn(self.client.get(self.message_url()).status_code, (403, 404))
                response = self.client.post(self.message_url(), {
                    "recipient": self.admin.pk, "body": "Unauthorized message.",
                })
                self.assertIn(response.status_code, (403, 404))
        self.assertFalse(RescueCaseMessage.objects.exists())

    def test_messages_restrict_recipient_to_admin_or_active_assignee(self):
        self.assign()
        for sender, invalid_recipients in (
            (self.admin, (self.reporter, self.other_operator, self.manager)),
            (self.assignee, (self.reporter, self.other_operator, self.inactive_admin)),
        ):
            self.client.force_login(sender)
            for recipient in invalid_recipients:
                with self.subTest(sender=sender.email, recipient=recipient.email):
                    self.client.post(self.message_url(), {
                        "recipient": recipient.pk, "body": "Invalid recipient.",
                    })
                    self.assertFalse(RescueCaseMessage.objects.exists())
        self.client.force_login(self.admin)
        self.client.post(self.message_url(), {"recipient": self.assignee.pk, "body": "  "})
        self.assertFalse(RescueCaseMessage.objects.exists())

    def test_messages_and_read_receipts_are_scoped_to_sender_and_recipient(self):
        self.assign()
        self.assign(user=self.other_operator)
        addressed = RescueCaseMessage.objects.create(
            rescue_case=self.private_case, sender=self.admin, recipient=self.assignee,
            body="Only the assigned rescuer sees this instruction.",
        )
        third_party = RescueCaseMessage.objects.create(
            rescue_case=self.private_case, sender=self.other_admin, recipient=self.other_operator,
            body="Another private conversation.",
        )
        outbound = RescueCaseMessage.objects.create(
            rescue_case=self.private_case, sender=self.assignee, recipient=self.admin,
            body="An unread reply addressed to admin.",
        )
        self.client.force_login(self.assignee)
        response = self.client.get(self.message_url())
        self.assertContains(response, addressed.body)
        self.assertNotContains(response, third_party.body)
        addressed.refresh_from_db()
        third_party.refresh_from_db()
        outbound.refresh_from_db()
        self.assertIsNotNone(addressed.read_at)
        self.assertIsNone(third_party.read_at)
        self.assertIsNone(outbound.read_at)
        self.client.force_login(self.admin)
        admin_response = self.client.get(self.message_url())
        self.assertNotContains(admin_response, third_party.body)
        outbound.refresh_from_db()
        third_party.refresh_from_db()
        self.assertIsNotNone(outbound.read_at)
        self.assertIsNone(third_party.read_at)

    def test_inactive_assignment_revokes_private_messaging_access(self):
        assignment = self.assign()
        assignment.is_active = False
        assignment.save(update_fields=("is_active",))
        self.client.force_login(self.assignee)
        self.assertIn(self.client.get(self.message_url()).status_code, (403, 404))
        self.client.post(self.message_url(), {
            "recipient": self.admin.pk, "body": "Assignment has ended.",
        })
        self.assertFalse(RescueCaseMessage.objects.exists())

    def test_admin_and_assignee_can_still_message_after_case_is_closed(self):
        self.assign()
        self.private_case.change_status(
            RescueCase.Status.CLOSED, changed_by=self.admin, note="Reviewed and finalized.",
        )
        self.client.force_login(self.admin)
        self.client.post(self.message_url(), {
            "recipient": self.assignee.pk, "body": "Thank you; review is complete.",
        })
        self.assertTrue(RescueCaseMessage.objects.filter(
            rescue_case=self.private_case, sender=self.admin, recipient=self.assignee,
        ).exists())
        self.client.force_login(self.assignee)
        self.assertEqual(self.client.get(self.message_url()).status_code, 200)
        self.client.post(self.message_url(), {
            "recipient": self.admin.pk, "body": "Acknowledged after final review.",
        })
        self.assertTrue(RescueCaseMessage.objects.filter(
            rescue_case=self.private_case, sender=self.assignee, recipient=self.admin,
            body="Acknowledged after final review.",
        ).exists())
