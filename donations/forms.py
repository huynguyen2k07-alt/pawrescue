from django import forms

from organizations.models import OrganizationMembership, RescueOrganization
from rescue.models import RescueCase
from rescue.uploads import sanitize_image_upload

from .models import CampaignExpense, Donation, FundraisingCampaign
from .uploads import sanitize_receipt_upload


MANAGER_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.MANAGER,
)


def _managed_organizations(user):
    if user is None or not user.is_authenticated:
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


def _validate_upload_size(uploaded_file):
    if uploaded_file and uploaded_file.size > 5 * 1024 * 1024:
        raise forms.ValidationError("Tệp tải lên phải nhỏ hơn 5 MB.")
    return uploaded_file


class FundraisingCampaignForm(forms.ModelForm):
    class Meta:
        model = FundraisingCampaign
        fields = (
            "organization",
            "rescue_case",
            "title",
            "description",
            "target_amount",
            "cover_image",
            "bank_name",
            "bank_account_name",
            "bank_account_number",
            "transfer_content",
            "status",
            "starts_at",
            "ends_at",
        )
        labels = {
            "organization": "Tổ chức phụ trách",
            "rescue_case": "Ca cứu hộ liên quan",
            "title": "Tên chiến dịch",
            "description": "Mục tiêu và kế hoạch sử dụng",
            "target_amount": "Số tiền mục tiêu (VNĐ)",
            "cover_image": "Ảnh đại diện",
            "bank_name": "Ngân hàng",
            "bank_account_name": "Tên chủ tài khoản",
            "bank_account_number": "Số tài khoản",
            "transfer_content": "Nội dung chuyển khoản gợi ý",
            "status": "Trạng thái chiến dịch",
            "starts_at": "Ngày bắt đầu",
            "ends_at": "Ngày kết thúc",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "target_amount": forms.NumberInput(attrs={"min": 1, "step": 1000}),
            "cover_image": forms.ClearableFileInput(
                attrs={"accept": ".jpg,.jpeg,.png,.webp"}
            ),
            "starts_at": forms.DateInput(attrs={"type": "date"}),
            "ends_at": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        organizations = _managed_organizations(user)
        self.fields["organization"].queryset = organizations
        self.fields["rescue_case"].queryset = RescueCase.objects.filter(
            organization__in=organizations
        ).select_related("organization")
        self.fields["rescue_case"].required = False

    def clean_cover_image(self):
        uploaded_file = _validate_upload_size(
            self.cleaned_data.get("cover_image")
        )
        return sanitize_image_upload(uploaded_file) if uploaded_file else None

    def clean(self):
        cleaned_data = super().clean()
        organization = cleaned_data.get("organization")
        rescue_case = cleaned_data.get("rescue_case")
        if rescue_case and rescue_case.organization_id != getattr(
            organization,
            "pk",
            None,
        ):
            self.add_error(
                "rescue_case",
                "Ca cứu hộ phải thuộc tổ chức phụ trách chiến dịch.",
            )
        starts_at = cleaned_data.get("starts_at")
        ends_at = cleaned_data.get("ends_at")
        if starts_at and ends_at and ends_at < starts_at:
            self.add_error("ends_at", "Ngày kết thúc không thể trước ngày bắt đầu.")
        return cleaned_data


class DonationForm(forms.ModelForm):
    class Meta:
        model = Donation
        fields = (
            "donor_name",
            "donor_email",
            "amount",
            "method",
            "reference_code",
            "proof",
            "message",
            "is_anonymous",
        )
        labels = {
            "donor_name": "Họ và tên",
            "donor_email": "Email",
            "amount": "Số tiền đã ủng hộ (VNĐ)",
            "method": "Hình thức",
            "reference_code": "Mã giao dịch hoặc ghi chú",
            "proof": "Ảnh/PDF xác nhận chuyển khoản",
            "message": "Lời nhắn",
            "is_anonymous": "Ẩn tên trên trang công khai",
        }
        widgets = {
            "amount": forms.NumberInput(attrs={"min": 1, "step": 1000}),
            "proof": forms.ClearableFileInput(
                attrs={"accept": ".jpg,.jpeg,.png,.webp,.pdf"}
            ),
            "message": forms.Textarea(attrs={"rows": 3}),
            "is_anonymous": forms.CheckboxInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and user.is_authenticated and not self.is_bound:
            self.initial.setdefault("donor_name", user.full_name)
            self.initial.setdefault("donor_email", user.email)

    def clean_proof(self):
        uploaded_file = _validate_upload_size(self.cleaned_data.get("proof"))
        return sanitize_receipt_upload(uploaded_file) if uploaded_file else None


class CampaignExpenseForm(forms.ModelForm):
    class Meta:
        model = CampaignExpense
        fields = (
            "category",
            "amount",
            "description",
            "spent_at",
            "receipt",
            "is_receipt_public",
        )
        labels = {
            "category": "Hạng mục",
            "amount": "Số tiền (VNĐ)",
            "description": "Nội dung chi",
            "spent_at": "Ngày chi",
            "receipt": "Biên lai",
            "is_receipt_public": "Cho phép công khai biên lai",
        }
        widgets = {
            "amount": forms.NumberInput(attrs={"min": 1, "step": 1000}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "spent_at": forms.DateInput(attrs={"type": "date"}),
            "receipt": forms.ClearableFileInput(
                attrs={"accept": ".jpg,.jpeg,.png,.webp,.pdf"}
            ),
            "is_receipt_public": forms.CheckboxInput(),
        }

    def clean_receipt(self):
        uploaded_file = _validate_upload_size(self.cleaned_data.get("receipt"))
        return sanitize_receipt_upload(uploaded_file) if uploaded_file else None


class DonationReviewForm(forms.Form):
    status = forms.ChoiceField(
        choices=(
            (Donation.Status.CONFIRMED, "Xác nhận đã nhận"),
            (Donation.Status.REJECTED, "Đánh dấu không hợp lệ"),
        )
    )
