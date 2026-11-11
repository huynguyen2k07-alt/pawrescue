from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_cookie

from rescue.models import RescueCase
from rescue.permissions import visible_cases_for
from rescue.privacy import present_case

from .forms import (
    AddOrganizationMemberForm,
    MembershipRoleForm,
    RescueOrganizationForm,
)
from .models import OrganizationMembership, RescueOrganization


ACTIVE_CASE_STATUSES = (
    RescueCase.Status.REPORTED,
    RescueCase.Status.VERIFIED,
    RescueCase.Status.ASSIGNED,
    RescueCase.Status.IN_PROGRESS,
    RescueCase.Status.PENDING_REVIEW,
)


def _active_membership(user, organization):
    if not user.is_authenticated:
        return None
    if getattr(user, "is_moderator", False) and not user.is_superuser:
        return None
    return OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
        is_active=True,
    ).first()


def _is_owner(user, organization, membership=None):
    if user.is_superuser:
        return True
    membership = membership or _active_membership(user, organization)
    return bool(
        membership and membership.role == OrganizationMembership.Role.OWNER
    )


def _member_or_forbidden(user, organization):
    membership = _active_membership(user, organization)
    if user.is_superuser or membership:
        return membership, None
    return None, HttpResponseForbidden("Bạn không phải thành viên của tổ chức này.")


def _owner_or_forbidden(user, organization):
    membership = _active_membership(user, organization)
    if _is_owner(user, organization, membership):
        return membership, None
    return membership, HttpResponseForbidden(
        "Chỉ chủ tổ chức mới có quyền thực hiện thao tác này."
    )


@never_cache
@vary_on_cookie
@login_required
def dashboard(request):
    if getattr(request.user, "is_moderator", False) and not request.user.is_superuser:
        return HttpResponseForbidden("Cộng tác viên cứu hộ chỉ xử lý các ca được admin giao.")
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    ).select_related("organization")

    if request.user.is_superuser:
        organizations = RescueOrganization.objects.filter(is_active=True)
    else:
        organization_ids = memberships.values_list("organization_id", flat=True)
        organizations = RescueOrganization.objects.filter(id__in=organization_ids)

    organizations = organizations.annotate(
        active_case_count=Count(
            "rescue_cases",
            filter=(
                Q(rescue_cases__status__in=ACTIVE_CASE_STATUSES)
                & Q(rescue_cases__in=visible_cases_for(request.user, RescueCase.objects.all()))
            ),
            distinct=True,
        ),
        member_count=Count(
            "memberships",
            filter=Q(memberships__is_active=True),
            distinct=True,
        ),
    )

    role_by_organization = {
        membership.organization_id: membership.get_role_display()
        for membership in memberships
    }
    organization_list = list(organizations)
    for organization in organization_list:
        organization.current_role = role_by_organization.get(
            organization.id,
            "Quản trị viên hệ thống",
        )

    organization_ids = [organization.id for organization in organization_list]
    cases = visible_cases_for(
        request.user,
        RescueCase.objects.filter(organization_id__in=organization_ids)
        .select_related("organization", "reporter")
        .prefetch_related("images", "assignments__assignee"),
    )

    context = {
        "organizations": organization_list,
        "cases": [present_case(request.user, case) for case in cases],
        "can_manage_organization_features": (
            request.user.is_superuser
            or memberships.filter(
                role__in=(
                    OrganizationMembership.Role.OWNER,
                    OrganizationMembership.Role.MANAGER,
                )
            ).exists()
        ),
    }
    return render(request, "organizations/dashboard.html", context)


@never_cache
@vary_on_cookie
@login_required
def organization_create(request):
    if getattr(request.user, "is_moderator", False) and not request.user.is_superuser:
        return HttpResponseForbidden("Cộng tác viên cứu hộ không có quyền tạo tổ chức.")
    if request.method == "POST":
        form = RescueOrganizationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                organization = form.save(commit=False)
                organization.created_by = request.user
                organization.save()
                OrganizationMembership.objects.create(
                    organization=organization,
                    user=request.user,
                    role=OrganizationMembership.Role.OWNER,
                )

            messages.success(
                request,
                "Tổ chức đã được tạo. Bạn đang là chủ tổ chức.",
            )
            return redirect(
                "organizations:organization-detail",
                pk=organization.pk,
            )
    else:
        form = RescueOrganizationForm(
            initial={"email": request.user.email, "phone": request.user.phone}
        )

    return render(
        request,
        "organizations/organization_form.html",
        {"form": form, "is_create": True},
    )


@never_cache
@vary_on_cookie
@login_required
def organization_detail(request, pk):
    organization = get_object_or_404(RescueOrganization, pk=pk, is_active=True)
    membership, forbidden = _member_or_forbidden(request.user, organization)
    if forbidden:
        return forbidden

    memberships = organization.memberships.filter(is_active=True).select_related("user")
    can_view_member_contacts = _is_owner(request.user, organization, membership)
    member_rows = [
        SimpleNamespace(
            pk=item.pk,
            user_id=item.user_id,
            role=item.role,
            display_name=item.user.full_name.strip() or "Thành viên",
            display_email=(
                item.user.email if can_view_member_contacts or item.user_id == request.user.pk else ""
            ),
            get_role_display=lambda label=item.get_role_display(): label,
        )
        for item in memberships
    ]
    cases = visible_cases_for(
        request.user,
        organization.rescue_cases.select_related("organization", "reporter")
        .prefetch_related("images", "assignments__assignee")
        .all(),
    )
    context = {
        "organization": organization,
        "membership": membership,
        "memberships": member_rows,
        "cases": [present_case(request.user, case) for case in cases],
        "can_manage_members": (
            not organization.is_system
            and _is_owner(request.user, organization, membership)
        ),
        "add_member_form": AddOrganizationMemberForm(),
        "role_choices": OrganizationMembership.Role.choices,
    }
    return render(request, "organizations/organization_detail.html", context)


@never_cache
@vary_on_cookie
@login_required
def organization_update(request, pk):
    organization = get_object_or_404(RescueOrganization, pk=pk, is_active=True)
    _membership, forbidden = _owner_or_forbidden(request.user, organization)
    if forbidden:
        return forbidden

    if organization.is_system:
        messages.info(
            request, "Thông tin tổ chức hệ thống được quản lý trong trang quản trị."
        )
        return redirect("admin:organizations_rescueorganization_change", organization.pk)

    if request.method == "POST":
        form = RescueOrganizationForm(request.POST, instance=organization)
        if form.is_valid():
            form.save()
            messages.success(request, "Thông tin tổ chức đã được cập nhật.")
            return redirect("organizations:organization-detail", pk=pk)
    else:
        form = RescueOrganizationForm(instance=organization)

    return render(
        request,
        "organizations/organization_form.html",
        {"form": form, "organization": organization, "is_create": False},
    )


@never_cache
@vary_on_cookie
@require_POST
@login_required
def member_add(request, pk):
    organization = get_object_or_404(RescueOrganization, pk=pk, is_active=True)
    _membership, forbidden = _owner_or_forbidden(request.user, organization)
    if forbidden:
        return forbidden
    if organization.is_system:
        return HttpResponseForbidden("Tổ chức hệ thống không có thành viên sở hữu.")

    form = AddOrganizationMemberForm(request.POST)
    if form.is_valid():
        membership, created = OrganizationMembership.objects.get_or_create(
            organization=organization,
            user=form.user,
            defaults={"role": form.cleaned_data["role"]},
        )
        if created:
            messages.success(request, "Đã thêm thành viên vào tổ chức.")
        elif membership.is_active:
            messages.info(request, "Tài khoản này đã là thành viên của tổ chức.")
        else:
            membership.role = form.cleaned_data["role"]
            membership.is_active = True
            membership.save(update_fields=("role", "is_active"))
            messages.success(request, "Đã khôi phục thành viên vào tổ chức.")
    else:
        errors = [error for field_errors in form.errors.values() for error in field_errors]
        messages.error(
            request,
            errors[0] if errors else "Không thể thêm thành viên này.",
        )

    return redirect("organizations:organization-detail", pk=pk)


@never_cache
@vary_on_cookie
@require_POST
@login_required
def member_change_role(request, pk, membership_pk):
    organization = get_object_or_404(RescueOrganization, pk=pk, is_active=True)
    _owner_membership, forbidden = _owner_or_forbidden(request.user, organization)
    if forbidden:
        return forbidden

    form = MembershipRoleForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vai trò được chọn không hợp lệ.")
        return redirect("organizations:organization-detail", pk=pk)

    new_role = form.cleaned_data["role"]
    with transaction.atomic():
        membership = get_object_or_404(
            OrganizationMembership.objects.select_for_update().order_by(),
            pk=membership_pk,
            organization=organization,
            is_active=True,
        )
        owner_ids = list(
            organization.memberships.select_for_update()
            .filter(role=OrganizationMembership.Role.OWNER, is_active=True)
            .order_by()
            .values_list("pk", flat=True)
        )
        is_last_owner = (
            membership.role == OrganizationMembership.Role.OWNER
            and new_role != OrganizationMembership.Role.OWNER
            and len(owner_ids) == 1
        )
        if is_last_owner:
            messages.error(request, "Tổ chức phải luôn có ít nhất một chủ sở hữu.")
        else:
            membership.role = new_role
            membership.save(update_fields=("role",))
            messages.success(request, "Vai trò thành viên đã được cập nhật.")

    return redirect("organizations:organization-detail", pk=pk)


@never_cache
@vary_on_cookie
@require_POST
@login_required
def member_remove(request, pk, membership_pk):
    organization = get_object_or_404(RescueOrganization, pk=pk, is_active=True)
    _owner_membership, forbidden = _owner_or_forbidden(request.user, organization)
    if forbidden:
        return forbidden

    with transaction.atomic():
        membership = get_object_or_404(
            OrganizationMembership.objects.select_for_update().order_by(),
            pk=membership_pk,
            organization=organization,
            is_active=True,
        )
        owner_ids = list(
            organization.memberships.select_for_update()
            .filter(role=OrganizationMembership.Role.OWNER, is_active=True)
            .order_by()
            .values_list("pk", flat=True)
        )
        is_last_owner = (
            membership.role == OrganizationMembership.Role.OWNER
            and len(owner_ids) == 1
        )
        if is_last_owner:
            messages.error(request, "Không thể xóa chủ sở hữu duy nhất của tổ chức.")
        else:
            membership.is_active = False
            membership.save(update_fields=("is_active",))
            messages.success(request, "Thành viên đã được gỡ khỏi tổ chức.")

    return redirect("organizations:organization-detail", pk=pk)
