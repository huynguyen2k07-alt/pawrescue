from .models import FundraisingCampaign


def donation_footer(request):
    # ===== CHỨC NĂNG CHÍNH: HIỂN THỊ THÔNG TIN ỦNG HỘ =====
    # Chỉ công khai tài khoản ngân hàng đầy đủ của quỹ đang hoạt động thuộc tổ chức đã xác minh.
    campaign = (
        FundraisingCampaign.objects.filter(
            status=FundraisingCampaign.Status.ACTIVE,
            organization__is_active=True,
            organization__is_verified=True,
        )
        .exclude(bank_name="")
        .exclude(bank_account_name="")
        .exclude(bank_account_number="")
        .select_related("organization")
        .order_by("-created_at", "-pk")
        .first()
    )
    return {"footer_donation_campaign": campaign}
