from django import forms
from django.core.validators import FileExtensionValidator
from django.db.models import Q

from organizations.models import OrganizationMembership, RescueOrganization
from rescue.models import RescueCase

from .models import (
    AdoptionApplication,
    AdoptionFollowUp,
    AdoptionSafetyReport,
    AnimalProfile,
)


MANAGER_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.MANAGER,
)


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
        if len(cleaned_files) > 6:
            raise forms.ValidationError("Bạn chỉ có thể tải tối đa 6 ảnh.")
        for uploaded_file in cleaned_files:
            if uploaded_file.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Mỗi ảnh phải nhỏ hơn 5 MB.")
        return cleaned_files


class AnimalProfileForm(forms.ModelForm):
    images = MultipleFileField(
        required=False,
        label="Ảnh hồ sơ",
        help_text="Tối đa 6 ảnh JPG, PNG hoặc WebP; mỗi ảnh dưới 5 MB.",
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
        widget=MultipleFileInput(attrs={"accept": ".jpg,.jpeg,.png,.webp"}),
    )

    class Meta:
        model = AnimalProfile
        fields = (
            "organization",
            "rescue_case",
            "name",
            "animal_type",
            "breed",
            "sex",
            "age_group",
            "estimated_age",
            "size",
            "color",
            "description",
            "temperament",
            "health_status",
            "vaccination_status",
            "is_neutered",
            "special_needs",
            "location",
            "status",
        )
        labels = {
            "organization": "Tổ chức phụ trách",
            "rescue_case": "Ca cứu hộ liên quan",
            "name": "Tên gọi",
            "animal_type": "Loại động vật",
            "breed": "Giống",
            "sex": "Giới tính",
            "age_group": "Nhóm tuổi",
            "estimated_age": "Tuổi ước tính",
            "size": "Kích thước",
            "color": "Màu sắc",
            "description": "Câu chuyện và mô tả",
            "temperament": "Tính cách",
            "health_status": "Tình trạng sức khỏe",
            "vaccination_status": "Tiêm phòng",
            "is_neutered": "Đã triệt sản",
            "special_needs": "Nhu cầu chăm sóc đặc biệt",
            "location": "Khu vực hiện tại",
            "status": "Trạng thái nhận nuôi",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "temperament": forms.Textarea(attrs={"rows": 3}),
            "health_status": forms.Textarea(attrs={"rows": 3}),
            "special_needs": forms.Textarea(attrs={"rows": 3}),
            "is_neutered": forms.CheckboxInput(),
        }

    def __init__(self, *args, user=None, require_images=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_images = require_images
        if user is None or not user.is_authenticated:
            organizations = RescueOrganization.objects.none()
        elif user.is_superuser:
            organizations = RescueOrganization.objects.filter(is_active=True)
        else:
            organizations = RescueOrganization.objects.filter(
                memberships__user=user,
                memberships__is_active=True,
                memberships__role__in=MANAGER_ROLES,
                is_active=True,
            ).distinct()
        self.fields["organization"].queryset = organizations

        eligible_cases = RescueCase.objects.filter(
            organization__in=organizations,
            status__in=(RescueCase.Status.RESCUED, RescueCase.Status.CLOSED),
        )
        if self.instance.pk and self.instance.rescue_case_id:
            eligible_cases = eligible_cases.filter(
                Q(adoption_profile__isnull=True)
                | Q(pk=self.instance.rescue_case_id)
            )
        else:
            eligible_cases = eligible_cases.filter(adoption_profile__isnull=True)
        self.fields["rescue_case"].queryset = eligible_cases.select_related(
            "organization"
        )
        self.fields["rescue_case"].required = False

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
                "Ca cứu hộ phải thuộc tổ chức phụ trách hồ sơ.",
            )
        if self.require_images and not cleaned_data.get("images"):
            self.add_error("images", "Hãy thêm ít nhất một ảnh cho hồ sơ nhận nuôi.")
        return cleaned_data


class AdoptionApplicationForm(forms.ModelForm):
    class Meta:
        model = AdoptionApplication
        fields = (
            "applicant_name",
            "phone",
            "address",
            "housing_type",
            "has_children",
            "other_pets",
            "pet_experience",
            "reason",
            "agrees_no_resale",
            "agrees_return_to_organization",
            "agrees_follow_up",
        )
        labels = {
            "applicant_name": "Họ và tên",
            "phone": "Số điện thoại",
            "address": "Địa chỉ",
            "housing_type": "Loại nhà ở",
            "has_children": "Gia đình có trẻ em",
            "other_pets": "Vật nuôi hiện có",
            "pet_experience": "Kinh nghiệm chăm sóc động vật",
            "reason": "Vì sao bạn muốn nhận nuôi",
            "agrees_no_resale": (
                "Tôi cam kết không bán, trao đổi, nhân giống thương mại hoặc tự ý "
                "chuyển động vật cho người khác."
            ),
            "agrees_return_to_organization": (
                "Nếu không thể tiếp tục chăm sóc, tôi sẽ liên hệ và bàn giao lại "
                "cho tổ chức phụ trách."
            ),
            "agrees_follow_up": (
                "Tôi đồng ý để tổ chức liên hệ kiểm tra tình trạng sau nhận nuôi."
            ),
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "other_pets": forms.Textarea(attrs={"rows": 3}),
            "pet_experience": forms.Textarea(attrs={"rows": 3}),
            "reason": forms.Textarea(attrs={"rows": 4}),
            "has_children": forms.CheckboxInput(),
            "agrees_no_resale": forms.CheckboxInput(),
            "agrees_return_to_organization": forms.CheckboxInput(),
            "agrees_follow_up": forms.CheckboxInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None and user.is_authenticated and not self.is_bound:
            self.initial.setdefault("applicant_name", user.full_name)
            self.initial.setdefault("phone", user.phone)
        for field_name in (
            "agrees_no_resale",
            "agrees_return_to_organization",
            "agrees_follow_up",
        ):
            self.fields[field_name].required = True
            self.fields[field_name].error_messages["required"] = (
                "Bạn cần đồng ý đầy đủ cam kết bảo vệ động vật."
            )


class AdoptionReviewForm(forms.Form):
    status = forms.ChoiceField(
        label="Kết quả xét duyệt",
        choices=(
            (AdoptionApplication.Status.REVIEWING, "Đang xét duyệt"),
            (AdoptionApplication.Status.APPROVED, "Chấp thuận"),
            (AdoptionApplication.Status.REJECTED, "Không phù hợp"),
        ),
    )
    review_note = forms.CharField(
        required=False,
        label="Ghi chú phản hồi",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    identity_confirmed = forms.BooleanField(
        required=False,
        label="Đã đối chiếu danh tính và thông tin liên hệ của người đăng ký",
    )

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("status") == AdoptionApplication.Status.APPROVED
            and not cleaned_data.get("identity_confirmed")
        ):
            self.add_error(
                "identity_confirmed",
                "Cần xác nhận đã đối chiếu danh tính trước khi chấp thuận.",
            )
        return cleaned_data


class AdoptionFollowUpForm(forms.ModelForm):
    class Meta:
        model = AdoptionFollowUp
        fields = ("contact_method", "outcome", "notes")
        labels = {
            "contact_method": "Hình thức liên hệ",
            "outcome": "Kết quả theo dõi",
            "notes": "Ghi chú và bằng chứng",
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class AdoptionSafetyReportForm(forms.ModelForm):
    class Meta:
        model = AdoptionSafetyReport
        fields = ("reason", "description", "evidence_url")
        labels = {
            "reason": "Vấn đề cần báo cáo",
            "description": "Mô tả chi tiết",
            "evidence_url": "Liên kết bằng chứng (nếu có)",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "Nêu thời gian, địa điểm và những gì bạn quan sát được...",
                }
            ),
            "evidence_url": forms.URLInput(
                attrs={"placeholder": "https://..."}
            ),
        }


class AdoptionSafetyReviewForm(forms.Form):
    status = forms.ChoiceField(
        label="Kết quả xác minh",
        choices=(
            (AdoptionSafetyReport.Status.REVIEWING, "Đang xác minh"),
            (AdoptionSafetyReport.Status.CONFIRMED, "Xác nhận vi phạm"),
            (AdoptionSafetyReport.Status.DISMISSED, "Không đủ căn cứ"),
        ),
    )
    review_note = forms.CharField(
        required=False,
        label="Ghi chú xử lý",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
