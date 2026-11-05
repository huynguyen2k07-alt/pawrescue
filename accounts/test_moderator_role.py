from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.test import TestCase
from django.urls import reverse

from accounts.permissions import is_support_operator, support_operator_queryset
from donations.models import Donation, FundraisingCampaign
from organizations.models import OrganizationMembership, RescueOrganization
from organizations.permissions import can_manage_organization, fundraising_organizations
from rescue.models import RescueAssignment, RescueCase
from rescue.permissions import is_rescue_moderator
from support.models import SupportConversation, SupportMessage


class ModeratorAccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="moderator-role-main@example.com", password="test-password",
        )
        cls.moderator = users.objects.create_user(
            email="moderator-role-operator@example.com", password="test-password",
            full_name="Quản trị viên cứu hộ", role=users.Role.MODERATOR,
        )
        cls.reporter = users.objects.create_user(
            email="moderator-role-reporter@example.com", password="test-password",
        )
        cls.conversation = SupportConversation.objects.create(
            user=cls.reporter, subject="Hộp thư riêng không được giao",
        )
        SupportMessage.objects.create(
            conversation=cls.conversation, sender=cls.reporter,
            sender_role=SupportMessage.SenderRole.USER,
            body="Thông tin riêng chỉ nhân sự hỗ trợ được đọc.",
        )

    def create_case(self, title, status=RescueCase.Status.REPORTED):
        return RescueCase.objects.create(
            title=title, description="Mô tả riêng của tin báo", animal_type="cat",
            reporter=self.reporter, address=f"Địa chỉ riêng của {title}",
            latitude="16.054407", longitude="108.202167", status=status,
            is_location_private=True,
        )

    def add_accidental_privileges(self, source="direct"):
        self.moderator.is_staff = True
        self.moderator.save(update_fields=("is_staff",))
        self.moderator.user_permissions.clear()
        self.moderator.groups.clear()
        permissions = Permission.objects.filter(
            content_type__app_label__in=("accounts", "support", "organizations", "donations", "rescue"),
        )
        if source == "group":
            group, _created = Group.objects.get_or_create(name="Quyền cấp nhầm cho quản trị viên")
            group.permissions.set(permissions)
            self.moderator.groups.add(group)
        else:
            self.moderator.user_permissions.set(permissions)
        return get_user_model().objects.get(pk=self.moderator.pk)

    def test_moderator_has_no_staff_superuser_or_support_privileges(self):
        self.assertTrue(self.moderator.is_moderator)
        self.assertTrue(is_rescue_moderator(self.moderator))
        self.assertFalse(self.moderator.is_staff)
        self.assertFalse(self.moderator.is_superuser)
        self.assertEqual(self.moderator.get_all_permissions(), set())
        self.assertFalse(is_support_operator(self.moderator))
        self.assertFalse(
            support_operator_queryset(get_user_model()).filter(pk=self.moderator.pk).exists()
        )

    def test_only_active_moderator_role_is_recognized(self):
        self.assertFalse(is_rescue_moderator(AnonymousUser()))
        self.assertFalse(is_rescue_moderator(self.reporter))
        self.moderator.is_active = False
        self.assertFalse(is_rescue_moderator(self.moderator))

    def test_registration_cannot_grant_moderator_or_staff_privileges(self):
        response = self.client.post(reverse("accounts:register"), {
            "email": "forged-moderator@example.com",
            "full_name": "Người dùng đăng ký",
            "phone": "0901234567",
            "password1": "A-strong-password-2026",
            "password2": "A-strong-password-2026",
            "role": get_user_model().Role.MODERATOR,
            "is_staff": "on",
            "is_superuser": "on",
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email="forged-moderator@example.com")
        self.assertEqual(user.role, user.Role.MEMBER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(is_rescue_moderator(user))

    def test_workspace_opens_before_first_assignment_without_support_inbox_data(self):
        unrelated_case = self.create_case("Tin báo chưa được giao")
        self.client.force_login(self.moderator)

        response = self.client.get(reverse("collaborators:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["rescue_has_workspace"])
        self.assertFalse(response.context["support_is_operator"])
        self.assertEqual(list(response.context["active_cases"]), [])
        self.assertEqual(response.context["reported_count"], 0)
        for key in (
            "recent_conversations", "open_conversation_count", "unread_message_count",
        ):
            self.assertNotIn(key, response.context)
        self.assertNotContains(response, unrelated_case.title)
        self.assertNotContains(response, unrelated_case.address)
        self.assertNotContains(response, self.conversation.subject)
        self.assertNotContains(response, self.reporter.email)
        self.assertNotContains(response, reverse("support:inbox"))

    def test_workspace_shows_only_currently_assigned_active_cases(self):
        assigned_case = self.create_case("Ca được admin giao")
        unassigned_case = self.create_case("Ca chưa giao cho quản trị viên")
        revoked_case = self.create_case("Ca đã thu hồi phân công")
        completed_case = self.create_case("Ca đã hoàn tất", RescueCase.Status.RESCUED)
        for rescue_case, is_active in (
            (assigned_case, True), (revoked_case, False), (completed_case, True),
        ):
            RescueAssignment.objects.create(
                rescue_case=rescue_case, assignee=self.moderator,
                assigned_by=self.admin, is_active=is_active,
            )
        self.client.force_login(self.moderator)

        response = self.client.get(reverse("collaborators:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["active_cases"]), [assigned_case])
        self.assertEqual(response.context["reported_count"], 1)
        self.assertContains(response, assigned_case.title)
        self.assertContains(response, assigned_case.address)
        for rescue_case in (unassigned_case, revoked_case, completed_case):
            self.assertNotContains(response, rescue_case.title)
            self.assertNotContains(response, rescue_case.address)

    def test_moderator_cannot_open_support_inbox_or_django_admin(self):
        self.client.force_login(self.moderator)
        response = self.client.get(reverse("support:inbox"))
        self.assertEqual(response.status_code, 403)
        for url in (
            reverse("admin:index"), reverse("admin:accounts_user_changelist"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("admin:login")))

    def test_pending_result_remains_in_assigned_workspace_until_admin_approval(self):
        rescue_case = self.create_case(
            "Ca đang chờ admin duyệt kết quả", RescueCase.Status.PENDING_REVIEW,
        )
        RescueAssignment.objects.create(
            rescue_case=rescue_case, assignee=self.moderator, assigned_by=self.admin,
        )
        self.client.force_login(self.moderator)

        response = self.client.get(reverse("collaborators:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["active_cases"]), [rescue_case])
        self.assertEqual(response.context["reported_count"], 1)
        self.assertContains(response, RescueCase.Status.PENDING_REVIEW.label)

    def test_staff_and_direct_or_group_permissions_cannot_open_global_inbox_or_admin(self):
        for source in ("direct", "group"):
            with self.subTest(permission_source=source):
                moderator = self.add_accidental_privileges(source)
                self.assertFalse(is_support_operator(moderator))
                self.assertFalse(
                    support_operator_queryset(get_user_model()).filter(pk=moderator.pk).exists()
                )
                self.client.force_login(moderator)
                response = self.client.get(reverse("support:inbox"))
                self.assertEqual(response.status_code, 403)
                response = self.client.get(reverse("collaborators:dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("recent_conversations", response.context)
                self.assertNotIn("open_conversation_count", response.context)
                self.assertNotContains(response, self.conversation.subject)
                for url in (
                    reverse("admin:index"), reverse("admin:accounts_user_changelist"),
                    reverse("admin:accounts_user_change", args=(self.reporter.pk,)),
                ):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.url.startswith(reverse("admin:login")))

    def test_org_ownership_cannot_grant_moderator_org_or_financial_management(self):
        moderator = self.add_accidental_privileges()
        organization = RescueOrganization.objects.create(
            name="Tổ chức có quyền cấp nhầm", is_verified=True,
        )
        OrganizationMembership.objects.create(
            organization=organization, user=moderator,
            role=OrganizationMembership.Role.OWNER,
        )
        member = OrganizationMembership.objects.create(
            organization=organization, user=self.reporter,
            role=OrganizationMembership.Role.VOLUNTEER,
        )
        campaign = FundraisingCampaign.objects.create(
            organization=organization, title="Quỹ không thuộc quyền cứu hộ",
            description="Quỹ kiểm tra phân quyền", target_amount="1000000",
            status=FundraisingCampaign.Status.ACTIVE,
        )
        donation = Donation.objects.create(
            campaign=campaign, donor=self.reporter, donor_name="Người đóng góp",
            donor_email=self.reporter.email, amount="100000",
        )
        self.assertFalse(can_manage_organization(moderator, organization))
        self.assertEqual(list(fundraising_organizations(moderator)), [])
        self.client.force_login(moderator)

        for url in (
            reverse("organizations:dashboard"),
            reverse("organizations:organization-create"),
            reverse("organizations:organization-detail", args=(organization.pk,)),
            reverse("organizations:organization-update", args=(organization.pk,)),
            reverse("donations:dashboard"),
            reverse("donations:campaign-create"),
            reverse("donations:campaign-update", args=(campaign.pk,)),
            reverse("donations:expense-create", args=(campaign.pk,)),
        ):
            with self.subTest(method="GET", url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

        mutations = (
            ("organizations:organization-create", (), {"name": "Tổ chức tạo trái quyền"}),
            ("organizations:organization-update", (organization.pk,), {"name": "Tên sửa trái quyền"}),
            ("organizations:member-add", (organization.pk,), {"email": self.admin.email, "role": "manager"}),
            ("organizations:member-change-role", (organization.pk, member.pk), {"role": "manager"}),
            ("organizations:member-remove", (organization.pk, member.pk), {}),
            ("donations:campaign-create", (), {"organization": organization.pk}),
            ("donations:campaign-update", (campaign.pk,), {"title": "Quỹ sửa trái quyền"}),
            ("donations:expense-create", (campaign.pk,), {"amount": "1000"}),
            ("donations:donation-review", (donation.pk,), {"status": Donation.Status.CONFIRMED}),
        )
        for route, arguments, payload in mutations:
            with self.subTest(method="POST", route=route):
                self.assertEqual(
                    self.client.post(reverse(route, args=arguments), payload).status_code, 403,
                )

        organization.refresh_from_db()
        member.refresh_from_db()
        donation.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(organization.name, "Tổ chức có quyền cấp nhầm")
        self.assertFalse(RescueOrganization.objects.filter(name="Tổ chức tạo trái quyền").exists())
        self.assertEqual(organization.memberships.count(), 2)
        self.assertEqual(member.role, OrganizationMembership.Role.VOLUNTEER)
        self.assertTrue(member.is_active)
        self.assertEqual(donation.status, Donation.Status.PENDING)
        self.assertEqual(campaign.title, "Quỹ không thuộc quyền cứu hộ")
        self.assertEqual(campaign.expenses.count(), 0)

    def test_superuser_keeps_global_rights_even_if_moderator_role_is_selected(self):
        self.admin.role = self.admin.Role.MODERATOR
        self.admin.save(update_fields=("role",))
        self.assertTrue(is_support_operator(self.admin))
        self.assertTrue(
            support_operator_queryset(get_user_model()).filter(pk=self.admin.pk).exists()
        )
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
