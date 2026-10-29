from django.contrib.auth import get_user_model
from django.db.models import Q

from accounts.permissions import support_operator_queryset
from organizations.models import OrganizationMembership

from .models import RescueCase


def is_rescue_admin(user):
    # Quyền điều hành cứu hộ chỉ dành cho tài khoản quản trị cao nhất đang hoạt động.
    return bool(user and user.is_authenticated and user.is_active and user.is_superuser)


def is_case_assignee(user, rescue_case):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return rescue_case.assignments.filter(assignee=user, is_active=True).exists()


def visible_cases_for(user, queryset):
    # Tin báo mới chỉ hiện với quản trị viên, người báo tin và người đang được phân công.
    if is_rescue_admin(user):
        return queryset
    if not user or not user.is_authenticated or not user.is_active:
        return queryset.exclude(status=RescueCase.Status.REPORTED)
    return queryset.filter(
        ~Q(status=RescueCase.Status.REPORTED)
        | Q(reporter=user)
        | Q(assignments__assignee=user, assignments__is_active=True)
    ).distinct()


def eligible_assignees():
    # Quản trị viên chỉ giao ca cho nhân sự hỗ trợ hoặc chủ, điều phối viên của tổ chức hợp lệ.
    user_model = get_user_model()
    member_ids = OrganizationMembership.objects.filter(
        is_active=True,
        organization__is_active=True,
        organization__is_verified=True,
        organization__is_system=False,
        role__in=(OrganizationMembership.Role.OWNER, OrganizationMembership.Role.MANAGER),
    ).values_list("user_id", flat=True)
    operator_ids = support_operator_queryset(user_model).values_list("pk", flat=True)
    return user_model.objects.filter(is_active=True).filter(
        Q(pk__in=operator_ids) | Q(pk__in=member_ids)
    ).distinct().order_by("full_name", "email")
