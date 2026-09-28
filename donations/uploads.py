from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from rescue.uploads import sanitize_image_upload


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
PDF_SUFFIXES = {".pdf"}


def sanitize_receipt_upload(uploaded_file):
    """Verify an evidence upload by its bytes, not only its file extension."""
    original_name = Path(getattr(uploaded_file, "name", "document")).name
    suffix = Path(original_name).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return sanitize_image_upload(uploaded_file)
    if suffix not in PDF_SUFFIXES:
        raise ValidationError("Chỉ chấp nhận ảnh JPG, PNG, WebP hoặc tệp PDF.")

    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except (AttributeError, OSError, ValueError) as error:
        raise ValidationError("Không thể đọc tệp chứng từ.") from error

    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise ValidationError("Nội dung tệp không phải PDF hợp lệ.")

    result = ContentFile(data, name=original_name[:180])
    result.content_type = "application/pdf"
    return result


def sanitize_model_receipt(instance, field_name):
    field_file = getattr(instance, field_name, None)
    if not field_file or getattr(field_file, "_committed", True):
        return
    cleaned = sanitize_receipt_upload(field_file.file)
    field_file.save(cleaned.name, cleaned, save=False)
