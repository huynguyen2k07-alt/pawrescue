import mimetypes
from decimal import Decimal
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST

from organizations.models import OrganizationMembership, RescueOrganization
from rescue.models import Notification, RescueCase
from rescue.notifications import create_notifications

from .forms import (
    CampaignExpenseForm,
    DonationForm,
    DonationReviewForm,
    FundraisingCampaignForm,
)
from .models import CampaignExpense, Donation, FundraisingCampaign


MANAGER_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.MANAGER,
)
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=0)


def _managed_organizations(user):
    if not user.is_authenticated:
        return RescueOrganization.objects.none()
    if user.is_superuser:
        return RescueOrganization.objects.filter(is_active=True)
    return RescueOrganization.objects.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__role__in=MANAGER_ROLES,
        is_verified=True,
        is_active=True,
    ).distinct()


def _can_manage_campaign(user, campaign):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not campaign.organization.is_active or not campaign.organization.is_verified:
        return False
    return OrganizationMembership.objects.filter(
        organization=campaign.organization,
        user=user,
        is_active=True,
        role__in=MANAGER_ROLES,
    ).exists()


def _manager_ids(organization):
    if not organization.is_active or not organization.is_verified:
        return ()
    return organization.memberships.filter(
        is_active=True,
        role__in=MANAGER_ROLES,
        user__is_active=True,
    ).values_list("user_id", flat=True)


def _private_file_response(field_file):
    try:
        file_handle = field_file.open("rb")
    except (FileNotFoundError, OSError, ValueError) as error:
        raise Http404 from error

    filename = Path(field_file.name).name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = FileResponse(file_handle, content_type=content_type)
    response.headers["Content-Disposition"] = content_disposition_header(
        False,
        filename,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _campaigns_with_financials(queryset=None):
    if queryset is None:
        queryset = FundraisingCampaign.objects.all()
    confirmed_subquery = (
        Donation.objects.filter(
            campaign_id=OuterRef("pk"),
            status=Donation.Status.CONFIRMED,
        )
        .values("campaign_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    expense_subquery = (
        CampaignExpense.objects.filter(campaign_id=OuterRef("pk"))
        .values("campaign_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    return queryset.annotate(
        confirmed_total=Coalesce(
            Subquery(confirmed_subquery, output_field=MONEY_FIELD),
            Value(Decimal("0")),
            output_field=MONEY_FIELD,
        ),
        expense_total=Coalesce(
            Subquery(expense_subquery, output_field=MONEY_FIELD),
            Value(Decimal("0")),
            output_field=MONEY_FIELD,
        ),
        donation_count=Count(
            "donations",
            filter=Q(donations__status=Donation.Status.CONFIRMED),
        ),
    )


def campaign_list(request):
    campaigns = _campaigns_with_financials(
        FundraisingCampaign.objects.filter(
            organization__is_active=True,
            organization__is_verified=True,
        ).exclude(status=FundraisingCampaign.Status.DRAFT)
    ).select_related("organization", "rescue_case")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        campaigns = campaigns.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(organization__name__icontains=query)
        )
    public_statuses = {
        FundraisingCampaign.Status.ACTIVE,
        FundraisingCampaign.Status.COMPLETED,
        FundraisingCampaign.Status.CLOSED,
    }
    if status in public_statuses:
        campaigns = campaigns.filter(status=status)
    context = {
        "page_obj": Paginator(
            campaigns.order_by("-created_at", "-pk"),
            9,
        ).get_page(request.GET.get("page")),
        "query": query,
        "selected_status": status,
        "status_choices": [
            choice
            for choice in FundraisingCampaign.Status.choices
            if choice[0] != FundraisingCampaign.Status.DRAFT
        ],
        "can_manage_funds": _managed_organizations(request.user).exists(),
    }
    return render(request, "donations/campaign_list.html", context)


def campaign_detail(request, pk):
    campaign = get_object_or_404(
        _campaigns_with_financials().select_related(
            "organization",
            "rescue_case",
        ),
        pk=pk,
    )
    can_manage = _can_manage_campaign(request.user, campaign)
    if (
        not campaign.organization.is_active
        or not campaign.organization.is_verified
    ) and not request.user.is_superuser:
        raise Http404
    if campaign.status == FundraisingCampaign.Status.DRAFT and not can_manage:
        raise Http404
    donations = campaign.donations.filter(
        status=Donation.Status.CONFIRMED
    ).select_related("donor", "confirmed_by")[:30]
    expenses = campaign.expenses.select_related("recorded_by")
    context = {
        "campaign": campaign,
        "donations": donations,
        "expenses": expenses,
        "can_manage": can_manage,
        "can_donate": (
            campaign.status == FundraisingCampaign.Status.ACTIVE
            and campaign.organization.is_active
            and campaign.organization.is_verified
        ),
        "donation_form": DonationForm(user=request.user),
    }
    return render(request, "donations/campaign_detail.html", context)


@login_required
def campaign_create(request):
    if not _managed_organizations(request.user).exists():
        return HttpResponseForbidden(
            "Bạn cần là chủ hoặc điều phối viên để tạo chiến dịch."
        )
    if request.method == "POST":
        form = FundraisingCampaignForm(
            request.POST,
            request.FILES,
            user=request.user,
        )
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.created_by = request.user
            campaign.save()
            messages.success(request, "Chiến dịch gây quỹ đã được tạo.")
            return redirect("donations:campaign-detail", pk=campaign.pk)
    else:
        form = FundraisingCampaignForm(user=request.user)
        case_id = request.GET.get("case")
        if case_id:
            rescue_case = form.fields["rescue_case"].queryset.filter(pk=case_id).first()
            if rescue_case:
                form.initial.update(
                    {
                        "organization": rescue_case.organization,
                        "rescue_case": rescue_case,
                        "title": f"Chung tay hỗ trợ: {rescue_case.title}",
                        "description": rescue_case.description,
                        "transfer_content": f"CUUHO {rescue_case.pk}",
                    }
                )
    return render(
        request,
        "donations/campaign_form.html",
        {"form": form, "is_create": True},
    )


@login_required
def campaign_update(request, pk):
    campaign = get_object_or_404(FundraisingCampaign, pk=pk)
    if not _can_manage_campaign(request.user, campaign):
        return HttpResponseForbidden("Bạn không có quyền sửa chiến dịch này.")
    if request.method == "POST":
        form = FundraisingCampaignForm(
            request.POST,
            request.FILES,
            instance=campaign,
            user=request.user,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Chiến dịch đã được cập nhật.")
            return redirect("donations:campaign-detail", pk=campaign.pk)
    else:
        form = FundraisingCampaignForm(instance=campaign, user=request.user)
    return render(
        request,
        "donations/campaign_form.html",
        {"form": form, "campaign": campaign, "is_create": False},
    )


@require_POST
@login_required
def donation_create(request, pk):
    with transaction.atomic():
        campaign = get_object_or_404(
            FundraisingCampaign.objects.select_for_update().select_related(
                "organization"
            ),
            pk=pk,
            organization__is_active=True,
            organization__is_verified=True,
        )
        if campaign.status != FundraisingCampaign.Status.ACTIVE:
            messages.error(request, "Chiến dịch hiện không nhận thêm đóng góp.")
            return redirect("donations:campaign-detail", pk=pk)
        form = DonationForm(request.POST, request.FILES, user=request.user)
        if not form.is_valid():
            errors = [
                str(error)
                for field_errors in form.errors.values()
                for error in field_errors
            ]
            messages.error(
                request,
                errors[0] if errors else "Không thể ghi nhận đóng góp.",
            )
            return redirect("donations:campaign-detail", pk=pk)
        donation = form.save(commit=False)
        donation.campaign = campaign
        donation.donor = request.user
        donation.save()
        create_notifications(
            recipient_ids=_manager_ids(campaign.organization),
            kind=Notification.Kind.DONATION_SUBMITTED,
            title="Có đóng góp mới cần xác nhận",
            message=(
                f'{donation.donor_name} vừa khai báo đóng góp '
                f'{donation.amount:,.0f} VNĐ cho "{campaign.title}".'
            ),
            actor=request.user,
            target_url=reverse("donations:dashboard"),
        )
    messages.success(
        request,
        "Đã gửi thông tin đóng góp. Tổ chức sẽ xác nhận sau khi kiểm tra.",
    )
    return redirect("donations:my-donations")


@login_required
def my_donations(request):
    donations = request.user.donations.select_related(
        "campaign",
        "campaign__organization",
    )
    return render(
        request,
        "donations/my_donations.html",
        {"donations": donations},
    )


@require_GET
def donation_proof(request, pk):
    donation = get_object_or_404(
        Donation.objects.select_related("campaign__organization"),
        pk=pk,
    )
    can_access = request.user.is_authenticated and (
        request.user.is_superuser
        or donation.donor_id == request.user.pk
        or _can_manage_campaign(request.user, donation.campaign)
    )
    if not can_access or not donation.proof:
        raise Http404
    return _private_file_response(donation.proof)


@require_GET
def expense_receipt(request, pk):
    expense = get_object_or_404(
        CampaignExpense.objects.select_related("campaign__organization"),
        pk=pk,
    )
    public_receipt = (
        expense.is_receipt_public
        and expense.campaign.status != FundraisingCampaign.Status.DRAFT
        and expense.campaign.organization.is_active
        and expense.campaign.organization.is_verified
    )
    if not public_receipt and not _can_manage_campaign(request.user, expense.campaign):
        raise Http404
    if not expense.receipt:
        raise Http404
    return _private_file_response(expense.receipt)


@login_required
def dashboard(request):
    organizations = _managed_organizations(request.user)
    if not organizations.exists():
        return HttpResponseForbidden(
            "Bạn cần là chủ hoặc điều phối viên để quản lý quỹ."
        )
    status = request.GET.get("status", "").strip()
    campaigns = _campaigns_with_financials(
        FundraisingCampaign.objects.filter(organization__in=organizations)
    ).select_related("organization", "rescue_case")
    donations = Donation.objects.filter(
        campaign__organization__in=organizations
    ).select_related("campaign", "donor")
    if status in Donation.Status.values:
        donations = donations.filter(status=status)
    confirmed_total = Donation.objects.filter(
        campaign__organization__in=organizations,
        status=Donation.Status.CONFIRMED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    expense_total = CampaignExpense.objects.filter(
        campaign__organization__in=organizations
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    context = {
        "campaigns": campaigns.order_by("-created_at"),
        "donations": donations,
        "selected_status": status,
        "donation_status_choices": Donation.Status.choices,
        "review_status_choices": DonationReviewForm.base_fields["status"].choices,
        "confirmed_total": confirmed_total,
        "expense_total": expense_total,
        "balance_total": confirmed_total - expense_total,
    }
    return render(request, "donations/dashboard.html", context)


@require_POST
@login_required
def donation_review(request, pk):
    form = DonationReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Kết quả xác nhận không hợp lệ.")
        return redirect("donations:dashboard")
    with transaction.atomic():
        donation = get_object_or_404(
            Donation.objects.select_for_update().select_related(
                "campaign",
                "campaign__organization",
                "donor",
            ),
            pk=pk,
        )
        if not _can_manage_campaign(request.user, donation.campaign):
            return HttpResponseForbidden("Bạn không có quyền xác nhận đóng góp này.")
        if donation.status != Donation.Status.PENDING:
            messages.info(request, "Đóng góp này đã được xử lý trước đó.")
            return redirect("donations:dashboard")
        new_status = form.cleaned_data["status"]
        donation.status = new_status
        donation.confirmed_by = request.user
        donation.confirmed_at = (
            timezone.now() if new_status == Donation.Status.CONFIRMED else None
        )
        donation.save(
            update_fields=("status", "confirmed_by", "confirmed_at")
        )
        if new_status == Donation.Status.CONFIRMED:
            confirmed_total = donation.campaign.donations.filter(
                status=Donation.Status.CONFIRMED
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
            if (
                confirmed_total >= donation.campaign.target_amount
                and donation.campaign.status == FundraisingCampaign.Status.ACTIVE
            ):
                donation.campaign.status = FundraisingCampaign.Status.COMPLETED
                donation.campaign.save(update_fields=("status", "updated_at"))
        if donation.donor_id:
            create_notifications(
                recipient_ids=(donation.donor_id,),
                kind=Notification.Kind.DONATION_REVIEWED,
                title="Đóng góp của bạn đã được cập nhật",
                message=(
                    f'Khoản đóng góp {donation.amount:,.0f} VNĐ cho '
                    f'"{donation.campaign.title}" hiện ở trạng thái '
                    f'“{donation.get_status_display()}”.'
                ),
                actor=request.user,
                target_url=reverse("donations:my-donations"),
            )
    messages.success(request, "Trạng thái đóng góp đã được cập nhật.")
    return redirect("donations:dashboard")


@login_required
def expense_create(request, campaign_pk):
    campaign = get_object_or_404(FundraisingCampaign, pk=campaign_pk)
    if not _can_manage_campaign(request.user, campaign):
        return HttpResponseForbidden(
            "Bạn không có quyền ghi chi phí cho chiến dịch này."
        )
    if request.method == "POST":
        form = CampaignExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.campaign = campaign
            expense.recorded_by = request.user
            expense.save()
            messages.success(request, "Khoản chi đã được thêm vào sổ minh bạch.")
            return redirect("donations:campaign-detail", pk=campaign.pk)
    else:
        form = CampaignExpenseForm(initial={"spent_at": timezone.localdate()})
    return render(
        request,
        "donations/expense_form.html",
        {"form": form, "campaign": campaign},
    )
