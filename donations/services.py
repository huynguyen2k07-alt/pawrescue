from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from rescue.models import Notification
from rescue.notifications import create_notifications

from .models import Donation, FundraisingCampaign


@transaction.atomic
def save_reviewed_donation(donation, *, reviewer, pending_only=False):
    """Lưu người duyệt và kết quả duyệt đóng góp nhất quán giữa các giao diện."""
    # ===== CHỨC NĂNG CHÍNH: DUYỆT KHOẢN ĐÓNG GÓP =====
    # Mọi giao diện dùng chung giao dịch duyệt để nhất quán người duyệt, tổng quỹ và thông báo.
    campaign = FundraisingCampaign.objects.select_for_update().get(
        pk=donation.campaign_id
    )
    previous = (
        Donation.objects.select_for_update().filter(pk=donation.pk).first()
        if donation.pk else None
    )
    if pending_only and (
        previous is None
        or previous.status != Donation.Status.PENDING
        or previous.campaign_id != donation.campaign_id
    ):
        return None
    previous_status = previous.status if previous else None
    if previous:
        donation.confirmed_by = previous.confirmed_by
        donation.confirmed_at = previous.confirmed_at
    status_changed = donation.status != previous_status
    if donation.status == Donation.Status.PENDING:
        donation.confirmed_by = None
        donation.confirmed_at = None
    elif status_changed:
        donation.confirmed_by = reviewer
        donation.confirmed_at = (
            timezone.now() if donation.status == Donation.Status.CONFIRMED else None
        )
    elif donation.status == Donation.Status.CONFIRMED:
        donation.confirmed_by = donation.confirmed_by or reviewer
        donation.confirmed_at = donation.confirmed_at or timezone.now()
    else:
        donation.confirmed_at = None

    donation.save()
    if donation.status == Donation.Status.CONFIRMED:
        confirmed_total = campaign.donations.filter(
            status=Donation.Status.CONFIRMED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        if (
            confirmed_total >= campaign.target_amount
            and campaign.status == FundraisingCampaign.Status.ACTIVE
        ):
            campaign.status = FundraisingCampaign.Status.COMPLETED
            campaign.save(update_fields=("status", "updated_at"))

    if status_changed and donation.status != Donation.Status.PENDING and donation.donor_id:
        create_notifications(
            recipient_ids=(donation.donor_id,),
            kind=Notification.Kind.DONATION_REVIEWED,
            title="Đóng góp của bạn đã được cập nhật",
            message=(
                f'Khoản đóng góp {donation.amount:,.0f} VNĐ cho '
                f'"{campaign.title}" hiện ở trạng thái '
                f'“{donation.get_status_display()}”.'
            ),
            actor=reviewer,
            target_url=reverse("donations:my-donations"),
        )
    return donation
