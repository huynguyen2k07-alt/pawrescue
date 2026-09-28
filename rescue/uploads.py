import struct
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile


MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_EDGE = 12_000
JPEG_METADATA_MARKERS = {0xE1, 0xED, 0xFE}
PNG_METADATA_CHUNKS = {b"eXIf", b"iTXt", b"tEXt", b"zTXt"}
WEBP_METADATA_CHUNKS = {b"EXIF", b"XMP "}


def _validate_dimensions(width, height):
    if width < 1 or height < 1:
        raise ValidationError("Ảnh có kích thước không hợp lệ.")
    if width > MAX_IMAGE_EDGE or height > MAX_IMAGE_EDGE:
        raise ValidationError("Mỗi cạnh ảnh phải nhỏ hơn 12.000 pixel.")
    if width * height > MAX_IMAGE_PIXELS:
        raise ValidationError("Ảnh vượt quá giới hạn 40 triệu pixel.")


def _sanitize_jpeg(data):
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        raise ValidationError("Tệp JPEG không hợp lệ.")

    output = bytearray(data[:2])
    position = 2
    dimensions = None
    while position < len(data):
        marker_start = position
        if data[position] != 0xFF:
            raise ValidationError("Cấu trúc JPEG không hợp lệ.")
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            raise ValidationError("Tệp JPEG bị thiếu dữ liệu.")
        marker = data[position]
        position += 1

        if marker == 0xD9:
            output.extend(data[marker_start:position])
            break
        if marker == 0xDA:
            output.extend(data[marker_start:])
            position = len(data)
            break
        if marker in range(0xD0, 0xD8) or marker == 0x01:
            output.extend(data[marker_start:position])
            continue
        if position + 2 > len(data):
            raise ValidationError("Tệp JPEG bị thiếu dữ liệu.")
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2:
            raise ValidationError("Phân đoạn JPEG không hợp lệ.")
        segment_end = position + segment_length
        if segment_end > len(data):
            raise ValidationError("Tệp JPEG bị cắt ngắn.")

        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if segment_length < 7:
                raise ValidationError("Thông tin kích thước JPEG không hợp lệ.")
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            dimensions = (width, height)

        if marker not in JPEG_METADATA_MARKERS:
            output.extend(data[marker_start:segment_end])
        position = segment_end

    if dimensions is None:
        raise ValidationError("Không đọc được kích thước ảnh JPEG.")
    _validate_dimensions(*dimensions)
    return bytes(output), ".jpg", "image/jpeg"


def _sanitize_png(data):
    signature = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(signature):
        raise ValidationError("Tệp PNG không hợp lệ.")

    output = bytearray(signature)
    position = len(signature)
    saw_header = False
    saw_end = False
    while position + 12 <= len(data):
        chunk_start = position
        chunk_length = int.from_bytes(data[position : position + 4], "big")
        chunk_type = data[position + 4 : position + 8]
        chunk_end = position + 12 + chunk_length
        if chunk_end > len(data):
            raise ValidationError("Tệp PNG bị cắt ngắn.")
        if not saw_header:
            if chunk_type != b"IHDR" or chunk_length != 13:
                raise ValidationError("Phần đầu PNG không hợp lệ.")
            width, height = struct.unpack(">II", data[position + 8 : position + 16])
            _validate_dimensions(width, height)
            saw_header = True
        if chunk_type not in PNG_METADATA_CHUNKS:
            output.extend(data[chunk_start:chunk_end])
        position = chunk_end
        if chunk_type == b"IEND":
            saw_end = True
            break

    if not saw_header or not saw_end:
        raise ValidationError("Tệp PNG chưa hoàn chỉnh.")
    return bytes(output), ".png", "image/png"


def _sanitize_webp(data):
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValidationError("Tệp WebP không hợp lệ.")

    chunks = []
    position = 12
    dimensions = None
    while position + 8 <= len(data):
        chunk_type = data[position : position + 4]
        chunk_length = int.from_bytes(data[position + 4 : position + 8], "little")
        padded_length = chunk_length + (chunk_length % 2)
        chunk_end = position + 8 + padded_length
        if chunk_end > len(data):
            raise ValidationError("Tệp WebP bị cắt ngắn.")
        payload = bytearray(data[position + 8 : position + 8 + chunk_length])
        if chunk_type == b"VP8X" and chunk_length >= 10:
            payload[0] &= ~0x0C  # Clear EXIF and XMP feature flags.
            width = int.from_bytes(payload[4:7], "little") + 1
            height = int.from_bytes(payload[7:10], "little") + 1
            dimensions = (width, height)
        elif chunk_type == b"VP8 " and chunk_length >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            width = int.from_bytes(payload[6:8], "little") & 0x3FFF
            height = int.from_bytes(payload[8:10], "little") & 0x3FFF
            dimensions = (width, height)
        elif chunk_type == b"VP8L" and chunk_length >= 5 and payload[0] == 0x2F:
            dimension_bits = int.from_bytes(payload[1:5], "little")
            width = (dimension_bits & 0x3FFF) + 1
            height = ((dimension_bits >> 14) & 0x3FFF) + 1
            dimensions = (width, height)
        if chunk_type not in WEBP_METADATA_CHUNKS:
            chunk = bytearray(chunk_type)
            chunk.extend(len(payload).to_bytes(4, "little"))
            chunk.extend(payload)
            if len(payload) % 2:
                chunk.append(0)
            chunks.append(bytes(chunk))
        position = chunk_end

    if not chunks:
        raise ValidationError("Tệp WebP chưa hoàn chỉnh.")
    if dimensions is None:
        raise ValidationError("Không đọc được kích thước ảnh WebP.")
    _validate_dimensions(*dimensions)
    body = b"WEBP" + b"".join(chunks)
    cleaned = b"RIFF" + len(body).to_bytes(4, "little") + body
    return cleaned, ".webp", "image/webp"


def sanitize_image_upload(uploaded_file):
    """Validate image bytes and remove common EXIF/text metadata containers."""
    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except (AttributeError, OSError, ValueError) as error:
        raise ValidationError("Không thể đọc tệp ảnh.") from error

    if data.startswith(b"\xff\xd8"):
        cleaned, suffix, content_type = _sanitize_jpeg(data)
        allowed_suffixes = {".jpg", ".jpeg"}
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        cleaned, suffix, content_type = _sanitize_png(data)
        allowed_suffixes = {".png"}
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        cleaned, suffix, content_type = _sanitize_webp(data)
        allowed_suffixes = {".webp"}
    else:
        raise ValidationError("Nội dung tệp không phải JPG, PNG hoặc WebP hợp lệ.")

    original_name = Path(getattr(uploaded_file, "name", "image")).name
    original_suffix = Path(original_name).suffix.lower()
    if original_suffix not in allowed_suffixes:
        raise ValidationError("Đuôi tệp không khớp với nội dung ảnh thực tế.")

    safe_stem = Path(original_name).stem[:120] or "image"
    result = ContentFile(cleaned, name=f"{safe_stem}{suffix}")
    result.content_type = content_type
    return result


def sanitize_model_image(instance, field_name):
    """Normalize a newly assigned model image before its storage write."""
    field_file = getattr(instance, field_name, None)
    if not field_file or getattr(field_file, "_committed", True):
        return
    cleaned = sanitize_image_upload(field_file.file)
    field_file.save(cleaned.name, cleaned, save=False)
