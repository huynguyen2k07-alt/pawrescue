from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db import transaction
from django.utils import timezone

from organizations.models import RescueOrganization


class RescueCase(models.Model):
    class AnimalType(models.TextChoices):
        DOG = "dog", "Chó"
        CAT = "cat", "Mèo"
        BIRD = "bird", "Chim"
        WILDLIFE = "wildlife", "Động vật hoang dã"
        OTHER = "other", "Khác"

    class Urgency(models.TextChoices):
        LOW = "low", "Thấp"
        MEDIUM = "medium", "Trung bình"
        HIGH = "high", "Cao"
        CRITICAL = "critical", "Rất khẩn cấp"

    class Status(models.TextChoices):
        REPORTED = "reported", "Đã báo tin"
        VERIFIED = "verified", "Đã xác nhận"
        ASSIGNED = "assigned", "Đã phân công"
        IN_PROGRESS = "in_progress", "Đang cứu hộ"
        RESCUED = "rescued", "Đã cứu thành công"
        CLOSED = "closed", "Đã đóng"
        CANCELLED = "cancelled", "Đã hủy"

    title = models.CharField(max_length=200)
    description = models.TextField()
    animal_type = models.CharField(max_length=20, choices=AnimalType.choices)
    animal_details = models.CharField(max_length=255, blank=True)
    urgency = models.CharField(
        max_length=20,
        choices=Urgency.choices,
        default=Urgency.MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REPORTED,
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reported_rescue_cases",
        null=True,
        blank=True,
    )
    organization = models.ForeignKey(
        RescueOrganization,
        on_delete=models.SET_NULL,
        related_name="rescue_cases",
        null=True,
        blank=True,
    )
    contact_name = models.CharField(max_length=150, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField()
    is_location_private = models.BooleanField(
        default=False,
        help_text="Chỉ người báo tin và đội cứu hộ thấy vị trí chính xác.",
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=(
            MinValueValidator(Decimal("-90")),
            MaxValueValidator(Decimal("90")),
        ),
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=(
            MinValueValidator(Decimal("-180")),
            MaxValueValidator(Decimal("180")),
        ),
        null=True,
        blank=True,
    )
    reported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-reported_at",)

    def __str__(self):
        return f"#{self.pk} - {self.title}" if self.pk else self.title

    def change_status(self, new_status, changed_by=None, note=""):
        valid_statuses = {value for value, _label in self.Status.choices}
        if new_status not in valid_statuses:
            raise ValidationError({"status": "Invalid rescue case status."})

        if new_status == self.status:
            return None

        previous_status = self.status
        self.status = new_status
        if new_status in {
            self.Status.RESCUED,
            self.Status.CLOSED,
            self.Status.CANCELLED,
        }:
            self.closed_at = timezone.now()
        else:
            self.closed_at = None

        with transaction.atomic():
            self.save(update_fields=("status", "closed_at", "updated_at"))
            return CaseStatusHistory.objects.create(
                rescue_case=self,
                from_status=previous_status,
                to_status=new_status,
                changed_by=changed_by,
                note=note,
            )


class RescueCaseImage(models.Model):
    rescue_case = models.ForeignKey(
        RescueCase,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.FileField(
        upload_to="rescue_cases/%Y/%m/",
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
    )
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="uploaded_rescue_case_images",
        null=True,
        blank=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("uploaded_at",)

    def __str__(self):
        return f"Image for {self.rescue_case}"


class RescueAssignment(models.Model):
    rescue_case = models.ForeignKey(
        RescueCase,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rescue_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_rescue_assignments",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-assigned_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("rescue_case", "assignee"),
                name="unique_rescue_case_assignee",
            )
        ]

    def __str__(self):
        return f"{self.assignee} assigned to {self.rescue_case}"


class CaseStatusHistory(models.Model):
    rescue_case = models.ForeignKey(
        RescueCase,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(
        max_length=20,
        choices=RescueCase.Status.choices,
        blank=True,
    )
    to_status = models.CharField(max_length=20, choices=RescueCase.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="rescue_status_changes",
        null=True,
        blank=True,
    )
    note = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-changed_at",)
        verbose_name_plural = "case status histories"

    def __str__(self):
        return f"{self.rescue_case}: {self.from_status} -> {self.to_status}"


class RescueUpdate(models.Model):
    rescue_case = models.ForeignKey(
        RescueCase,
        on_delete=models.CASCADE,
        related_name="updates",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="rescue_updates",
        null=True,
        blank=True,
    )
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Update for {self.rescue_case} at {self.created_at}"


class RescueUpdateImage(models.Model):
    update = models.ForeignKey(
        RescueUpdate,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.FileField(
        upload_to="rescue_updates/%Y/%m/",
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("uploaded_at",)

    def __str__(self):
        return f"Image for update #{self.update_id}"


class Notification(models.Model):
    class Kind(models.TextChoices):
        CASE_CLAIMED = "case_claimed", "Ca đã được tiếp nhận"
        CASE_ASSIGNED = "case_assigned", "Ca đã được phân công"
        STATUS_CHANGED = "status_changed", "Trạng thái đã thay đổi"
        CASE_UPDATED = "case_updated", "Nhật ký cứu hộ mới"
        ADOPTION_SUBMITTED = "adoption_submitted", "Có đơn nhận nuôi mới"
        ADOPTION_REVIEWED = "adoption_reviewed", "Đơn nhận nuôi đã được xét duyệt"
        ADOPTION_SAFETY = "adoption_safety", "An toàn sau nhận nuôi"
        SUPPORT_MESSAGE = "support_message", "Tin nhắn hỗ trợ"
        DONATION_SUBMITTED = "donation_submitted", "Có đóng góp mới"
        DONATION_REVIEWED = "donation_reviewed", "Đóng góp đã được xác nhận"
        FEEDBACK_RECEIVED = "feedback_received", "Có góp ý mới"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="triggered_notifications",
        null=True,
        blank=True,
    )
    rescue_case = models.ForeignKey(
        RescueCase,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    target_url = models.CharField(max_length=255, blank=True)
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=180)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("recipient", "is_read", "-created_at"),
                name="notif_recipient_read_idx",
            )
        ]

    def __str__(self):
        return f"{self.recipient}: {self.title}"

    def mark_as_read(self):
        if self.is_read:
            return False
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=("is_read", "read_at"))
        return True


class KnowledgeArticle(models.Model):
    class Category(models.TextChoices):
        RESCUE = "rescue", "Kỹ năng cứu hộ"
        HEALTH = "health", "Sức khỏe thú cưng"
        CARE = "care", "Chăm sóc an toàn"

    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=240, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    excerpt = models.TextField(max_length=420)
    body = models.TextField()
    cover_image = models.FileField(
        upload_to="knowledge/%Y/%m/",
        blank=True,
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
    )
    static_image_path = models.CharField(max_length=255, blank=True)
    image_credit = models.CharField(max_length=180, blank=True)
    image_source_url = models.URLField(blank=True)
    source_name = models.CharField(max_length=180, blank=True)
    source_url = models.URLField(blank=True)
    is_published = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    published_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_featured", "-published_at")

    def __str__(self):
        return self.title


class ContributorProfile(models.Model):
    name = models.CharField(max_length=160)
    role = models.CharField(max_length=160)
    bio = models.TextField(max_length=520)
    photo = models.FileField(
        upload_to="contributors/%Y/%m/",
        blank=True,
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
    )
    static_image_path = models.CharField(max_length=255, blank=True)
    photo_credit = models.CharField(max_length=180, blank=True)
    photo_source_url = models.URLField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_order", "name")

    def __str__(self):
        return self.name


class CommunityFeedback(models.Model):
    class Category(models.TextChoices):
        GENERAL = "general", "Góp ý chung"
        FEATURE = "feature", "Đề xuất tính năng"
        PROBLEM = "problem", "Báo lỗi / vấn đề"
        PARTNERSHIP = "partnership", "Đề nghị hợp tác"

    class Status(models.TextChoices):
        NEW = "new", "Mới"
        REVIEWED = "reviewed", "Đã xem"
        CLOSED = "closed", "Đã xử lý"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="community_feedback",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=150)
    email = models.EmailField()
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.GENERAL,
    )
    message = models.TextField(max_length=3000)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-submitted_at",)

    def __str__(self):
        return f"{self.name} · {self.get_category_display()}"
