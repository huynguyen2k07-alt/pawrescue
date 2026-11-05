"""Kiểm thử việc thu hồi phân công làm mất quyền xử lý nhưng vẫn giữ lịch sử."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import (
    CaseStatusHistory,
    CommunityFeedback,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseMessage,
    RescueUpdate,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class AssignmentLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="lifecycle-admin@example.com", password="test-password", full_name="Admin điều phối",
        )
        cls.other_admin = users.objects.create_superuser(
            email="lifecycle-other-admin@example.com", password="test-password", full_name="Admin thứ hai",
        )
        cls.reporter = users.objects.create_user(
            email="lifecycle-reporter@example.com", password="test-password", full_name="Người báo tin",
        )
        cls.assignee = users.objects.create_user(
            email="lifecycle-assignee@example.com", password="test-password",
            full_name="Người phụ trách", role=users.Role.COLLABORATOR,
        )
        cls.other_assignee = users.objects.create_user(
            email="lifecycle-other-assignee@example.com", password="test-password",
            full_name="Đồng đội", role=users.Role.COLLABORATOR,
        )
        cls.staff = users.objects.create_user(
            email="lifecycle-staff@example.com", password="test-password", full_name="Nhân viên", is_staff=True,
        )
        cls.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="rescue"))
        cls.case = RescueCase.objects.create(
            title="Ca cần bảo vệ vị trí chính xác", description="Động vật đang cần sơ cứu.",
            animal_type=RescueCase.AnimalType.CAT, address="157 Nguyễn Văn Linh, Hải Châu, Đà Nẵng",
            latitude=Decimal("16.054407"), longitude=Decimal("108.202167"),
            is_location_private=True, reporter=cls.reporter, contact_name="Người báo tin", contact_phone="0901234567",
            status=RescueCase.Status.ASSIGNED,
        )
        cls.assignment = RescueAssignment.objects.create(
            rescue_case=cls.case, assignee=cls.assignee, assigned_by=cls.admin, notes="Mang lồng vận chuyển kín.",
        )
        cls.field_update = RescueUpdate.objects.create(
            rescue_case=cls.case, author=cls.assignee, note="Đã tiếp cận hiện trường.",
        )
        cls.private_message = RescueCaseMessage.objects.create(
            rescue_case=cls.case, sender=cls.admin, recipient=cls.assignee,
            body="Chỉ dẫn điều phối riêng cần giữ lại trong hồ sơ.",
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.assignee_client = Client()
        self.assignee_client.force_login(self.assignee)
        self.reporter_client = Client()
        self.reporter_client.force_login(self.reporter)

    def detail_url(self, case=None):
        return reverse("rescue:case-detail", args=((case or self.case).pk,))

    def revoke_url(self, case=None, assignment=None):
        return reverse("rescue:case-unassign", args=((case or self.case).pk, (assignment or self.assignment).pk))

    def assign(self):
        return self.client.post(reverse("rescue:case-assign", args=(self.case.pk,)), {
            "assignee": self.assignee.pk, "notes": "Chỉ dẫn mới sau khi giao lại.",
        })

    def test_main_admin_ends_assignment_preserves_work_and_notifies_assignee(self):
        response = self.client.post(self.revoke_url())
        self.assertRedirects(response, self.detail_url())
        self.assignment.refresh_from_db()
        self.case.refresh_from_db()
        self.assertFalse(self.assignment.is_active)
        self.assertIsNotNone(self.assignment.completed_at)
        self.assertEqual(self.assignment.assigned_by, self.admin)
        self.assertEqual(self.assignment.notes, "Mang lồng vận chuyển kín.")
        self.assertEqual(self.case.status, RescueCase.Status.ASSIGNED)
        self.assertIsNone(self.case.closed_at)
        self.assertTrue(RescueUpdate.objects.filter(pk=self.field_update.pk).exists())
        self.assertTrue(RescueCaseMessage.objects.filter(pk=self.private_message.pk).exists())
        history = CaseStatusHistory.objects.get(rescue_case=self.case)
        self.assertEqual(history.changed_by, self.admin)
        self.assertEqual(history.from_status, history.to_status)
        self.assertNotIn(self.assignee.full_name, history.note)
        notification = Notification.objects.get(recipient=self.assignee, rescue_case=self.case)
        self.assertEqual(notification.actor, self.admin)
        self.assertEqual(notification.target_url, reverse("rescue:notification-list"))
        self.assertContains(self.assignee_client.get(reverse("rescue:notification-list")), notification.title)

    def test_revocation_is_post_only_and_anonymous_users_must_sign_in(self):
        self.assertEqual(self.client.get(self.revoke_url()).status_code, 405)
        anonymous = Client()
        response = anonymous.post(self.revoke_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_active)

    def test_reporter_assignee_collaborator_and_staff_cannot_end_assignment(self):
        for user in (self.reporter, self.assignee, self.other_assignee, self.staff):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertEqual(self.client.post(self.revoke_url()).status_code, 403)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_active)
        self.assertIsNone(self.assignment.completed_at)
        self.assertFalse(self.case.status_history.exists())
        self.assertFalse(Notification.objects.exists())

    def test_cross_case_assignment_and_missing_objects_return_404(self):
        other_case = RescueCase.objects.create(
            title="Ca thứ hai", description="Ca khác", animal_type="dog", address="Đà Nẵng", reporter=self.reporter,
        )
        for url in (
            self.revoke_url(case=other_case),
            reverse("rescue:case-unassign", args=(self.case.pk, 999999)),
            reverse("rescue:case-unassign", args=(999999, self.assignment.pk)),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 404)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_active)
        self.assertFalse(self.case.status_history.exists())

    def test_ending_already_inactive_assignment_is_idempotent(self):
        self.client.post(self.revoke_url())
        self.assignment.refresh_from_db()
        ended_at = self.assignment.completed_at
        self.assertEqual(self.client.post(self.revoke_url()).status_code, 302)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.completed_at, ended_at)
        self.assertEqual(self.case.status_history.count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.assignee).count(), 1)

    def test_ended_assignment_loses_message_read_write_and_field_update_permission(self):
        message_url = reverse("rescue:case-messages", args=(self.case.pk,))
        self.assertContains(self.assignee_client.get(message_url), self.private_message.body)
        self.client.post(self.revoke_url())
        self.assertEqual(self.assignee_client.get(message_url).status_code, 404)
        self.assertEqual(self.assignee_client.post(message_url, {
            "recipient": self.admin.pk, "body": "Tin nhắn sau khi kết thúc phân công.",
        }).status_code, 404)
        self.assertEqual(self.assignee_client.post(
            reverse("rescue:case-add-update", args=(self.case.pk,)), {"note": "Cập nhật sau khi thu hồi quyền."},
        ).status_code, 403)
        self.assertEqual(self.case.private_messages.count(), 1)
        self.assertEqual(self.case.updates.count(), 1)

    def test_ended_assignment_loses_private_contact_address_and_exact_map_coordinates(self):
        before = self.assignee_client.get(self.detail_url())
        self.assertTrue(before.context["can_view_location"])
        self.assertTrue(before.context["can_view_contact"])
        self.assertFalse(before.context["map_is_approximate"])
        self.assertEqual(before.context["map_latitude"], float(self.case.latitude))
        self.assertEqual(before.context["map_longitude"], float(self.case.longitude))
        self.assertContains(before, self.case.address)
        self.client.post(self.revoke_url())
        after = self.assignee_client.get(self.detail_url())
        self.assertEqual(after.status_code, 200)
        self.assertFalse(after.context["can_view_location"])
        self.assertFalse(after.context["can_view_contact"])
        self.assertFalse(after.context["can_coordinate"])
        self.assertFalse(after.context["can_add_update"])
        self.assertTrue(after.context["map_is_approximate"])
        self.assertNotContains(after, self.case.address)
        self.assertNotContains(after, self.case.contact_phone)
        self.assertNotContains(after, self.assignment.notes)
        self.assertEqual(after.context["map_latitude"], round(float(self.case.latitude), 2))
        self.assertEqual(after.context["map_longitude"], round(float(self.case.longitude), 2))
        self.assertNotEqual(after.context["map_latitude"], float(self.case.latitude))
        self.assertNotEqual(after.context["map_longitude"], float(self.case.longitude))

    def test_main_admin_and_reporter_keep_exact_location_after_assignment_ends(self):
        self.client.post(self.revoke_url())
        for client in (self.client, self.reporter_client):
            with self.subTest(role="admin" if client is self.client else "reporter"):
                response = client.get(self.detail_url())
                self.assertTrue(response.context["can_view_location"])
                self.assertFalse(response.context["map_is_approximate"])
                self.assertContains(response, self.case.address)
                self.assertContains(response, self.case.contact_phone)

    def test_ending_one_assignment_preserves_other_active_assignee_access(self):
        teammate_assignment = RescueAssignment.objects.create(
            rescue_case=self.case, assignee=self.other_assignee, assigned_by=self.admin,
        )
        teammate_client = Client()
        teammate_client.force_login(self.other_assignee)
        self.client.post(self.revoke_url())
        teammate_assignment.refresh_from_db()
        self.assertTrue(teammate_assignment.is_active)
        response = teammate_client.get(self.detail_url())
        self.assertTrue(response.context["can_add_update"])
        self.assertTrue(response.context["can_view_location"])
        self.assertEqual(teammate_client.get(reverse("rescue:case-messages", args=(self.case.pk,))).status_code, 200)

    def test_reassigning_same_person_reuses_row_and_restores_access(self):
        original_pk = self.assignment.pk
        original_assigned_at = self.assignment.assigned_at
        self.client.post(self.revoke_url())
        response = self.assign()
        self.assertRedirects(response, self.detail_url())
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.pk, original_pk)
        self.assertEqual(self.assignment.assigned_at, original_assigned_at)
        self.assertTrue(self.assignment.is_active)
        self.assertIsNone(self.assignment.completed_at)
        self.assertEqual(self.assignment.notes, "Chỉ dẫn mới sau khi giao lại.")
        self.assertEqual(RescueAssignment.objects.filter(rescue_case=self.case, assignee=self.assignee).count(), 1)
        response = self.assignee_client.get(self.detail_url())
        self.assertTrue(response.context["can_add_update"])
        self.assertTrue(response.context["can_view_location"])
        self.assertFalse(response.context["map_is_approximate"])
        message_url = reverse("rescue:case-messages", args=(self.case.pk,))
        response = self.assignee_client.get(message_url)
        self.assertContains(response, self.private_message.body)
        self.assertContains(response, "Chỉ dẫn mới sau khi giao lại.")
        self.assertEqual(self.assignee_client.post(message_url, {
            "recipient": self.admin.pk, "body": "Đã nhận ca được giao lại.",
        }).status_code, 302)

    def test_admin_cannot_send_new_private_message_to_ended_assignee(self):
        self.client.post(self.revoke_url())
        message_url = reverse("rescue:case-messages", args=(self.case.pk,))
        response = self.client.post(message_url, {"recipient": self.assignee.pk, "body": "Tin nhắn gửi sai người đã gỡ."})
        self.assertEqual(response.status_code, 200)
        self.assertIn("recipient", response.context["form"].errors)
        self.assertEqual(self.case.private_messages.count(), 1)
        self.assertContains(response, self.private_message.body)

    def test_ending_assignment_after_final_review_preserves_terminal_status_and_time(self):
        for status in (RescueCase.Status.RESCUED, RescueCase.Status.CLOSED, RescueCase.Status.CANCELLED):
            with self.subTest(status=status):
                case = RescueCase.objects.create(
                    title=f"Hồ sơ kết thúc {status}", description="Hồ sơ đã được admin đánh giá.",
                    animal_type="cat", address="Đà Nẵng", reporter=self.reporter,
                )
                case.change_status(status, changed_by=self.admin, note="Admin xác nhận và chốt sổ.")
                closed_at = case.closed_at
                assignment = RescueAssignment.objects.create(
                    rescue_case=case, assignee=self.assignee, assigned_by=self.admin,
                )
                self.assertEqual(self.client.post(self.revoke_url(case, assignment)).status_code, 302)
                case.refresh_from_db()
                assignment.refresh_from_db()
                self.assertFalse(assignment.is_active)
                self.assertEqual(case.status, status)
                self.assertEqual(case.closed_at, closed_at)
                self.assertEqual(case.status_history.count(), 2)
                response = self.client.post(reverse("rescue:case-assign", args=(case.pk,)), {"assignee": self.assignee.pk})
                self.assertEqual(response.status_code, 302)
                assignment.refresh_from_db()
                self.assertFalse(assignment.is_active)
                case.refresh_from_db()
                self.assertEqual(case.closed_at, closed_at)


@override_settings(SECURE_SSL_REDIRECT=False)
class FeedbackAdminNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="feedback-notify-admin@example.com", password="test-password", full_name="Admin đang hoạt động",
        )
        cls.other_admin = users.objects.create_superuser(
            email="feedback-notify-other-admin@example.com", password="test-password", full_name="Admin thứ hai",
        )
        cls.inactive_admin = users.objects.create_superuser(
            email="feedback-notify-inactive@example.com", password="test-password", full_name="Admin đã khóa", is_active=False,
        )
        cls.member = users.objects.create_user(
            email="feedback-notify-member@example.com", password="test-password", full_name="Thành viên",
        )
        cls.operator = users.objects.create_user(
            email="feedback-notify-operator@example.com", password="test-password",
            full_name="Cộng tác viên", role=users.Role.COLLABORATOR,
        )
        cls.staff = users.objects.create_user(
            email="feedback-notify-staff@example.com", password="test-password", full_name="Nhân viên", is_staff=True,
        )
        cls.staff.user_permissions.set(Permission.objects.filter(content_type__app_label="rescue"))

    def submit_feedback(self):
        response = self.client.post(reverse("rescue:case-list"), {
            "name": "Người gửi góp ý", "email": "sender@example.com",
            "category": CommunityFeedback.Category.PROBLEM,
            "message": "Chi tiết phản hồi cần được admin chính xử lý.",
        })
        self.assertEqual(response.status_code, 302)
        return CommunityFeedback.objects.get()

    def assert_admin_recipients(self, feedback, expected_recipients):
        notifications = Notification.objects.filter(kind=Notification.Kind.FEEDBACK_RECEIVED)
        self.assertEqual(set(notifications.values_list("recipient_id", flat=True)), expected_recipients)
        expected_target = reverse("admin:rescue_communityfeedback_change", args=(feedback.pk,))
        self.assertEqual(set(notifications.values_list("target_url", flat=True)), {expected_target})
        for user in (self.operator, self.staff, self.member, self.inactive_admin):
            self.assertFalse(notifications.filter(recipient=user).exists())

    def test_member_feedback_notifies_only_active_main_admins_with_direct_admin_link(self):
        self.client.force_login(self.member)
        feedback = self.submit_feedback()
        self.assertEqual(feedback.user, self.member)
        self.assert_admin_recipients(feedback, {self.admin.pk, self.other_admin.pk})
        self.assertTrue(all(item.actor == self.member for item in Notification.objects.all()))

    def test_guest_feedback_notifies_only_active_main_admins_without_fabricated_actor(self):
        feedback = self.submit_feedback()
        self.assertIsNone(feedback.user)
        self.assert_admin_recipients(feedback, {self.admin.pk, self.other_admin.pk})
        self.assertFalse(Notification.objects.exclude(actor=None).exists())

    def test_admin_feedback_excludes_self_notification_and_keeps_other_admin_notified(self):
        self.client.force_login(self.admin)
        feedback = self.submit_feedback()
        self.assert_admin_recipients(feedback, {self.other_admin.pk})
