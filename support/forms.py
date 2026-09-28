from django import forms
from django.core.validators import FileExtensionValidator

from rescue.uploads import sanitize_image_upload

from .models import (
    IMAGE_EXTENSIONS,
    SUPPORT_ATTACHMENT_EXTENSIONS,
    VIDEO_EXTENSIONS,
)


IMAGE_CONTENT_TYPES = {
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
        validated_files = []
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
            if extension in IMAGE_EXTENSIONS:
                if uploaded_file.content_type not in IMAGE_CONTENT_TYPES:
                    raise forms.ValidationError(
                        f"Tệp {uploaded_file.name} không phải ảnh được hỗ trợ."
                    )
                validated_file = sanitize_image_upload(uploaded_file)
            else:
                if uploaded_file.content_type not in VIDEO_CONTENT_TYPES:
                    raise forms.ValidationError(
                        f"Tệp {uploaded_file.name} không phải video được hỗ trợ."
                    )
                uploaded_file.seek(0)
                header = uploaded_file.read(16)
                uploaded_file.seek(0)
                is_iso_video = (
                    extension in {"mp4", "mov"}
                    and len(header) >= 12
                    and header[4:8] == b"ftyp"
                )
                is_webm = extension == "webm" and header.startswith(
                    b"\x1a\x45\xdf\xa3"
                )
                if not (is_iso_video or is_webm):
                    raise forms.ValidationError(
                        f"Nội dung tệp {uploaded_file.name} không phải video hợp lệ."
                    )
                validated_file = uploaded_file
            if not validated_file:
                raise forms.ValidationError(
                    f"Tệp {uploaded_file.name} không phải ảnh hoặc video được hỗ trợ."
                )
            total_size += validated_file.size
            validated_files.append(validated_file)

        if total_size > 50 * 1024 * 1024:
            raise forms.ValidationError(
                "Tổng dung lượng tệp trong một tin nhắn phải nhỏ hơn 50 MB."
            )
        return validated_files


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
                "accept": ".jpg,.jpeg,.png,.webp,.mp4,.webm,.mov",
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
