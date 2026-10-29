from django import forms
from django.core.validators import FileExtensionValidator, MaxLengthValidator

from organizations.models import RescueOrganization
from organizations.permissions import managed_organizations

from .geography import is_within_da_nang
from .models import CommunityFeedback, RescueAssignment, RescueCase, RescueUpdate
from .permissions import eligible_assignees
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
        # Tin báo phải có đủ tọa độ trong phạm vi Đà Nẵng để xác định đúng hiện trường.
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
        self.fields["note"].label = "Đánh giá kết quả / ghi chú"
        self.fields["note"].help_text = (
            "Bắt buộc ghi đánh giá kết quả trước khi xác nhận cứu thành công, đóng hoặc hủy ca."
        )

    def clean(self):
        # Bắt buộc ghi đánh giá trước khi xác nhận cứu thành công, đóng hoặc hủy ca.
        cleaned_data = super().clean()
        if cleaned_data.get("status") in {
            RescueCase.Status.RESCUED,
            RescueCase.Status.CLOSED,
            RescueCase.Status.CANCELLED,
        } and not cleaned_data.get("note", "").strip():
            self.add_error("note", "Hãy ghi đánh giá kết quả trước khi chốt ca.")
        return cleaned_data


class RescueAssignmentForm(forms.ModelForm):
    class Meta:
        model = RescueAssignment
        fields = ("assignee", "notes")
        labels = {"assignee": "Người phụ trách", "notes": "Chỉ dẫn riêng cho người phụ trách"}
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = eligible_assignees()
        self.fields["notes"].max_length = 1500
        self.fields["notes"].validators.append(MaxLengthValidator(1500))


class CaseHandoffForm(forms.Form):
    organization = forms.ModelChoiceField(
        queryset=RescueOrganization.objects.none(),
        label="Đơn vị nhận xử lý",
        empty_label="Chọn đơn vị cứu hộ",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = RescueOrganization.objects.filter(
            is_active=True, is_verified=True, is_system=False,
        ).order_by("name")

    def clean_organization(self):
        organization = self.cleaned_data["organization"]
        if not (organization.phone.strip() or organization.email.strip()):
            raise forms.ValidationError("Hãy bổ sung số điện thoại hoặc email của đơn vị trước khi bàn giao.")
        return organization


class RescueCaseMessageForm(forms.Form):
    recipient = forms.ModelChoiceField(
        queryset=None,
        label="Gửi cho",
    )
    body = forms.CharField(
        max_length=2000,
        label="Tin nhắn riêng",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Trao đổi chỉ dành cho admin và người được phân công..."}),
    )

    def __init__(self, *args, recipients, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["recipient"].queryset = recipients
        if recipients.count() == 1:
            self.fields["recipient"].initial = recipients.first().pk


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
        self.fields["organization"].queryset = managed_organizations(user)


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
