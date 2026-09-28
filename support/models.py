from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from .storage import private_support_storage


IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
VIDEO_EXTENSIONS = ("mp4", "webm", "mov")
SUPPORT_ATTACHMENT_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS


def validate_support_attachment_size(uploaded_file):
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    maximum_size = 40 * 1024 * 1024 if extension in VIDEO_EXTENSIONS else 8 * 1024 * 1024
    if uploaded_file.size > maximum_size:
        limit = "40 MB" if extension in VIDEO_EXTENSIONS else "8 MB"
        raise ValidationError(f"Tệp này phải nhỏ hơn {limit}.")


class SupportConversation(models.Model):
    class Status(models.TextChoices):
        WAITING_ADMIN = "waiting_admin", "Chờ quản trị viên"
        WAITING_USER = "waiting_user", "Chờ người dùng"
        CLOSED = "closed", "Đã đóng"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_conversations",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_support_conversations",
        null=True,
        blank=True,
        limit_choices_to=(
            models.Q(is_superuser=True) | models.Q(role="collaborator")
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.WAITING_ADMIN,
    )
    subject = models.CharField(max_length=180, default="Hỗ trợ chung")
    last_message_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-last_message_at",)
        permissions = (
            ("handle_support", "Có thể xử lý hội thoại hỗ trợ"),
        )
        constraints = [
            models.UniqueConstraint(
                fields=("user",),
                condition=~models.Q(status="closed"),
                name="unique_active_support_conversation",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.get_status_display()}"


class SupportMessage(models.Model):
    class SenderRole(models.TextChoices):
        USER = "user", "Người dùng"
        ADMIN = "admin", "Quản trị viên"

    conversation = models.ForeignKey(
        SupportConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="support_messages",
    )
    sender_role = models.CharField(max_length=10, choices=SenderRole.choices)
    body = models.TextField(max_length=2000, blank=True, default="")
    is_read_by_admin = models.BooleanField(default=False)
    is_read_by_user = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
        indexes = [
            models.Index(
                fields=("conversation", "created_at"),
                name="support_conv_created_idx",
            ),
            models.Index(
                fields=("sender_role", "is_read_by_admin"),
                name="support_admin_unread_idx",
            ),
        ]

    def __str__(self):
        return f"Tin nhắn #{self.pk} - {self.conversation}"


class SupportAttachment(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Ảnh"
        VIDEO = "video", "Video"

    message = models.ForeignKey(
        SupportMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        storage=private_support_storage,
        upload_to="%Y/%m/",
        validators=(
            FileExtensionValidator(allowed_extensions=SUPPORT_ATTACHMENT_EXTENSIONS),
            validate_support_attachment_size,
        ),
    )
    media_type = models.CharField(max_length=10, choices=MediaType.choices)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("uploaded_at", "pk")

    def __str__(self):
        return f"{self.get_media_type_display()} cho tin nhắn #{self.message_id}"
