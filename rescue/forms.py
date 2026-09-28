from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator

from organizations.models import OrganizationMembership, RescueOrganization

from .geography import is_within_da_nang
from .models import CommunityFeedback, RescueAssignment, RescueCase, RescueUpdate
from .uploads import sanitize_image_upload


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if not data:
            return []

        files = data if isinstance(data, (list, tuple)) else [data]
        cleaned_files = [single_file_clean(item, initial) for item in files]

        if len(cleaned_files) > 5:
            raise forms.ValidationError("Bạn chỉ có thể tải tối đa 5 ảnh.")

        for uploaded_file in cleaned_files:
            if uploaded_file.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Mỗi ảnh phải nhỏ hơn 5 MB.")

        return [sanitize_image_upload(item) for item in cleaned_files]


class RescueCaseForm(forms.ModelForm):
    images = MultipleFileField(
        required=False,
        label="Ảnh hiện trường",
        help_text="Tối đa 5 ảnh JPG, PNG hoặc WebP; mỗi ảnh dưới 5 MB.",
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
        widget=MultipleFileInput(
            attrs={"accept": ".jpg,.jpeg,.png,.webp"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["latitude"].required = True
        self.fields["longitude"].required = True

    class Meta:
        model = RescueCase
        fields = (
            "title",
            "animal_type",
            "animal_details",
            "urgency",
            "description",
            "address",
            "is_location_private",
            "latitude",
            "longitude",
            "contact_name",
            "contact_phone",
        )
        labels = {
            "title": "Tiêu đề",
            "animal_type": "Loại động vật",
            "animal_details": "Đặc điểm nhận dạng",
            "urgency": "Mức độ khẩn cấp",
            "description": "Mô tả tình trạng",
            "address": "Địa chỉ",
            "is_location_private": "Ẩn vị trí chính xác với người ngoài",
            "latitude": "Vĩ độ",
            "longitude": "Kinh độ",
            "contact_name": "Tên người liên hệ",
            "contact_phone": "Số điện thoại liên hệ",
        }
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "Ví dụ: Chó bị thương gần chợ"}
            ),
            "animal_details": forms.TextInput(
                attrs={"placeholder": "Màu lông, kích thước, dấu hiệu nhận biết..."}
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Mô tả tình trạng và những gì bạn quan sát được",
                }
            ),
            "address": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Ví dụ: 430 Hùng Vương, Hải Châu, Đà Nẵng",
                }
            ),
            "is_location_private": forms.CheckboxInput(),
            "latitude": forms.NumberInput(
                attrs={"step": "0.000001", "min": "15.85", "max": "16.25"}
            ),
            "longitude": forms.NumberInput(
                attrs={"step": "0.000001", "min": "107.75", "max": "108.35"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")

        if (latitude is None) != (longitude is None):
            message = "Hãy chọn đầy đủ vị trí bằng cách đặt ghim trên bản đồ."
            if latitude is None:
                self.add_error("latitude", message)
            if longitude is None:
                self.add_error("longitude", message)
        elif latitude is not None and not is_within_da_nang(latitude, longitude):
            message = "PawRescue hiện chỉ tiếp nhận ca trong phạm vi Đà Nẵng."
            self.add_error("latitude", message)
            self.add_error("longitude", message)

        return cleaned_data


class CaseStatusUpdateForm(forms.Form):
    status = forms.ChoiceField(
        choices=RescueCase.Status.choices,
        label="Trạng thái mới",
    )
    note = forms.CharField(
        required=False,
        label="Ghi chú",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, current_status=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            choice
            for choice in RescueCase.Status.choices
            if choice[0] != current_status
        ]


class RescueAssignmentForm(forms.ModelForm):
    class Meta:
        model = RescueAssignment
        fields = ("assignee", "notes")
        labels = {"assignee": "Thành viên", "notes": "Ghi chú phân công"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        user_model = get_user_model()
        if organization is None:
            self.fields["assignee"].queryset = user_model.objects.none()
            return

        member_ids = OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
        ).values_list("user_id", flat=True)
        self.fields["assignee"].queryset = user_model.objects.filter(
            id__in=member_ids,
            is_active=True,
        ).order_by("full_name", "email")


class RescueUpdateForm(forms.ModelForm):
    images = MultipleFileField(
        required=False,
        label="Ảnh cập nhật",
        help_text="Tối đa 5 ảnh JPG, PNG hoặc WebP; mỗi ảnh dưới 5 MB.",
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
        widget=MultipleFileInput(
            attrs={"accept": ".jpg,.jpeg,.png,.webp"}
        ),
    )

    class Meta:
        model = RescueUpdate
        fields = ("note",)
        labels = {"note": "Nội dung cập nhật"}
        widgets = {
            "note": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Tình trạng hiện tại, việc đã làm và bước tiếp theo...",
                }
            )
        }


class ClaimOrganizationForm(forms.Form):
    organization = forms.ModelChoiceField(
        queryset=RescueOrganization.objects.none(),
        label="Tổ chức tiếp nhận",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is None or not user.is_authenticated:
            return

        if user.is_superuser:
            self.fields["organization"].queryset = RescueOrganization.objects.filter(
                is_active=True,
                is_verified=True,
            )
            return

        self.fields["organization"].queryset = RescueOrganization.objects.filter(
            memberships__user=user,
            memberships__is_active=True,
            memberships__role__in=(
                OrganizationMembership.Role.OWNER,
                OrganizationMembership.Role.MANAGER,
            ),
            is_active=True,
            is_verified=True,
            is_system=False,
        ).distinct()


class CommunityFeedbackForm(forms.ModelForm):
    website = forms.CharField(
        required=False,
        label="Website",
        widget=forms.HiddenInput(attrs={"autocomplete": "off", "tabindex": "-1"}),
    )

    class Meta:
        model = CommunityFeedback
        fields = ("name", "email", "category", "message")
        labels = {
            "name": "Họ và tên",
            "email": "Email",
            "category": "Chủ đề",
            "message": "Nội dung góp ý",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Tên của bạn"}),
            "email": forms.EmailInput(attrs={"placeholder": "ban@email.com"}),
            "message": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Bạn muốn PawRescue cải thiện điều gì?",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("website"):
            raise forms.ValidationError("Không thể gửi biểu mẫu này.")
        return cleaned_data
