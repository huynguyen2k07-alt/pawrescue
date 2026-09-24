from django import forms
from django.contrib.auth import get_user_model

from .models import OrganizationMembership, RescueOrganization


class RescueOrganizationForm(forms.ModelForm):
    class Meta:
        model = RescueOrganization
        fields = ("name", "description", "email", "phone", "address")
        labels = {
            "name": "Tên tổ chức",
            "description": "Giới thiệu",
            "email": "Email liên hệ",
            "phone": "Số điện thoại",
            "address": "Địa chỉ hoạt động",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Ví dụ: Nhóm cứu hộ Bàn Chân Nhỏ"}
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Mô tả khu vực hoạt động và năng lực cứu hộ",
                }
            ),
            "address": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Địa chỉ hoặc khu vực hoạt động"}
            ),
        }

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        duplicates = RescueOrganization.objects.filter(name__iexact=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Đã có một tổ chức sử dụng tên này.")
        return name


class AddOrganizationMemberForm(forms.Form):
    email = forms.EmailField(
        label="Email thành viên",
        widget=forms.EmailInput(
            attrs={"placeholder": "thanhvien@example.com", "autocomplete": "email"}
        ),
    )
    role = forms.ChoiceField(
        label="Vai trò",
        choices=(
            (
                OrganizationMembership.Role.MANAGER,
                OrganizationMembership.Role.MANAGER.label,
            ),
            (
                OrganizationMembership.Role.VOLUNTEER,
                OrganizationMembership.Role.VOLUNTEER.label,
            ),
        ),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        user_model = get_user_model()
        try:
            self.user = user_model.objects.get(email__iexact=email, is_active=True)
        except user_model.DoesNotExist as error:
            raise forms.ValidationError(
                "Chưa có tài khoản hoạt động nào sử dụng email này."
            ) from error
        return email


class MembershipRoleForm(forms.Form):
    role = forms.ChoiceField(
        label="Vai trò",
        choices=OrganizationMembership.Role.choices,
    )
