from django import forms
from django.core.validators import FileExtensionValidator

from .models import (
    IMAGE_EXTENSIONS,
    SUPPORT_ATTACHMENT_EXTENSIONS,
    VIDEO_EXTENSIONS,
)


IMAGE_CONTENT_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}
VIDEO_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class SupportAttachmentField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []

        files = data if isinstance(data, (list, tuple)) else [data]
        single_file_clean = super().clean
        cleaned_files = [single_file_clean(item, initial) for item in files]
        if len(cleaned_files) > 4:
            raise forms.ValidationError("Mỗi tin nhắn chỉ được gửi tối đa 4 tệp.")

        total_size = 0
        for uploaded_file in cleaned_files:
            extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
            maximum_size = (
                40 * 1024 * 1024
                if extension in VIDEO_EXTENSIONS
                else 8 * 1024 * 1024
            )
            if uploaded_file.size > maximum_size:
                limit = "40 MB" if extension in VIDEO_EXTENSIONS else "8 MB"
                raise forms.ValidationError(
                    f"Tệp {uploaded_file.name} phải nhỏ hơn {limit}."
                )
            expected_content_types = (
                IMAGE_CONTENT_TYPES
                if extension in IMAGE_EXTENSIONS
                else VIDEO_CONTENT_TYPES
            )
            if uploaded_file.content_type not in expected_content_types:
                raise forms.ValidationError(
                    f"Tệp {uploaded_file.name} không phải ảnh hoặc video được hỗ trợ."
                )
            total_size += uploaded_file.size

        if total_size > 50 * 1024 * 1024:
            raise forms.ValidationError(
                "Tổng dung lượng tệp trong một tin nhắn phải nhỏ hơn 50 MB."
            )
        return cleaned_files


class SupportMessageForm(forms.Form):
    body = forms.CharField(
        max_length=2000,
        strip=True,
        required=False,
        label="Nội dung",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Nhập nội dung cần hỗ trợ...",
            }
        ),
    )
    attachments = SupportAttachmentField(
        required=False,
        label="Ảnh hoặc video",
        validators=(
            FileExtensionValidator(
                allowed_extensions=SUPPORT_ATTACHMENT_EXTENSIONS
            ),
        ),
        widget=MultipleFileInput(
            attrs={
                "accept": ".jpg,.jpeg,.png,.webp,.gif,.mp4,.webm,.mov",
                "multiple": True,
            }
        ),
    )

    def clean_body(self):
        return self.cleaned_data.get("body", "").strip()

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("body") and not cleaned_data.get("attachments"):
            raise forms.ValidationError(
                "Hãy nhập nội dung hoặc chọn ít nhất một ảnh/video."
            )
        return cleaned_data
