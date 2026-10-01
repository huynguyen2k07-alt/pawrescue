from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from organizations.models import RescueOrganization
from rescue.models import RescueCase
from rescue.uploads import sanitize_model_image


class AnimalProfile(models.Model):
    class AnimalType(models.TextChoices):
        DOG = "dog", "Chó"
        CAT = "cat", "Mèo"
        BIRD = "bird", "Chim"
        OTHER = "other", "Khác"

    class AgeGroup(models.TextChoices):
        BABY = "baby", "Sơ sinh"
        YOUNG = "young", "Nhỏ tuổi"
        ADULT = "adult", "Trưởng thành"
        SENIOR = "senior", "Lớn tuổi"
        UNKNOWN = "unknown", "Chưa xác định"

    class Sex(models.TextChoices):
        MALE = "male", "Đực"
        FEMALE = "female", "Cái"
        UNKNOWN = "unknown", "Chưa xác định"

    class Size(models.TextChoices):
        SMALL = "small", "Nhỏ"
        MEDIUM = "medium", "Vừa"
        LARGE = "large", "Lớn"
        UNKNOWN = "unknown", "Chưa xác định"

    class VaccinationStatus(models.TextChoices):
        UNKNOWN = "unknown", "Chưa xác định"
        NOT_STARTED = "not_started", "Chưa tiêm"
        PARTIAL = "partial", "Đã tiêm một phần"
        COMPLETE = "complete", "Đã tiêm đầy đủ"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Đang tìm gia đình"
        PENDING = "pending", "Đang xét duyệt"
        HOLD = "hold", "Tạm dừng nhận đơn"
        ADOPTED = "adopted", "Đã được nhận nuôi"
        NOT_AVAILABLE = "not_available", "Chưa sẵn sàng"

    organization = models.ForeignKey(
        RescueOrganization,
        on_delete=models.CASCADE,
        related_name="adoption_profiles",
    )
    rescue_case = models.OneToOneField(
        RescueCase,
        on_delete=models.SET_NULL,
        related_name="adoption_profile",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_adoption_profiles",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    animal_type = models.CharField(max_length=20, choices=AnimalType.choices)
    breed = models.CharField(max_length=120, blank=True)
    sex = models.CharField(max_length=20, choices=Sex.choices, default=Sex.UNKNOWN)
    age_group = models.CharField(
        max_length=20,
        choices=AgeGroup.choices,
        default=AgeGroup.UNKNOWN,
    )
    estimated_age = models.CharField(max_length=80, blank=True)
    size = models.CharField(max_length=20, choices=Size.choices, default=Size.UNKNOWN)
    color = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    temperament = models.TextField()
    health_status = models.TextField()
    vaccination_status = models.CharField(
        max_length=20,
        choices=VaccinationStatus.choices,
        default=VaccinationStatus.UNKNOWN,
    )
    is_neutered = models.BooleanField(default=False)
    special_needs = models.TextField(blank=True)
    location = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    published_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    adopted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-published_at",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("adoptions:animal-detail", kwargs={"pk": self.pk})

    def mark_adopted(self):
        self.status = self.Status.ADOPTED
        self.adopted_at = timezone.now()
        self.save(update_fields=("status", "adopted_at", "updated_at"))


class AnimalProfileImage(models.Model):
    animal = models.ForeignKey(
        AnimalProfile,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.FileField(
        upload_to="adoption_animals/%Y/%m/",
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
    )
    caption = models.CharField(max_length=180, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("uploaded_at",)

    def __str__(self):
        return f"Image for {self.animal}"

    def save(self, *args, **kwargs):
        sanitize_model_image(self, "image")
        return super().save(*args, **kwargs)


class AdoptionApplication(models.Model):
    class HousingType(models.TextChoices):
        HOUSE = "house", "Nhà riêng"
        APARTMENT = "apartment", "Căn hộ"
        RENTAL = "rental", "Nhà thuê"
        OTHER = "other", "Khác"

    class Status(models.TextChoices):
        PENDING = "pending", "Đang chờ"
        REVIEWING = "reviewing", "Đang xét duyệt"
        APPROVED = "approved", "Đã chấp thuận"
        REJECTED = "rejected", "Không phù hợp"
        WITHDRAWN = "withdrawn", "Đã rút đơn"

    animal = models.ForeignKey(
        AnimalProfile,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="adoption_applications",
    )
    applicant_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    housing_type = models.CharField(max_length=20, choices=HousingType.choices)
    has_children = models.BooleanField(default=False)
    other_pets = models.TextField(blank=True)
    pet_experience = models.TextField(blank=True)
    reason = models.TextField()
    agrees_no_resale = models.BooleanField(default=False)
    agrees_return_to_organization = models.BooleanField(default=False)
    agrees_follow_up = models.BooleanField(default=False)
    pledge_accepted_at = models.DateTimeField(null=True, blank=True)
    identity_verified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_adoption_applications",
        null=True,
        blank=True,
    )
    review_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-submitted_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("animal", "applicant"),
                name="unique_animal_adoption_applicant",
            )
        ]

    def __str__(self):
        return f"{self.applicant} -> {self.animal}"

    @property
    def has_safety_pledge(self):
        return all(
            (
                self.agrees_no_resale,
                self.agrees_return_to_organization,
                self.agrees_follow_up,
                self.pledge_accepted_at,
            )
        )


class AdoptionPlacement(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Đang theo dõi"
        NEEDS_ATTENTION = "needs_attention", "Cần kiểm tra"
        FLAGGED = "flagged", "Nghi ngờ vi phạm"
        RETURNED = "returned", "Đã bàn giao lại"
        CLOSED = "closed", "Đã kết thúc theo dõi"

    application = models.OneToOneField(
        AdoptionApplication,
        on_delete=models.PROTECT,
        related_name="placement",
    )
    animal = models.ForeignKey(
        AnimalProfile,
        on_delete=models.PROTECT,
        related_name="placements",
    )
    adopter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="adoption_placements",
    )
    organization = models.ForeignKey(
        RescueOrganization,
        on_delete=models.PROTECT,
        related_name="adoption_placements",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    placed_at = models.DateTimeField(default=timezone.now)
    next_follow_up_on = models.DateField(null=True, blank=True)
    last_follow_up_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    manager_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("next_follow_up_on", "-placed_at")
        constraints = [
            models.UniqueConstraint(
                fields=("animal",),
                condition=models.Q(is_active=True),
                name="unique_active_animal_placement",
            )
        ]

    def __str__(self):
        return f"{self.animal} → {self.adopter}"


class AdoptionCheckInRequest(models.Model):
    class Milestone(models.IntegerChoices):
        MONTH_1 = 1, "Sau 1 tháng"
        MONTH_2 = 2, "Sau 2 tháng"
        MONTH_3 = 3, "Sau 3 tháng"

    class CareStatus(models.TextChoices):
        IN_CARE = "in_care", "Pet vẫn đang ở cùng tôi"
        NEEDS_SUPPORT = "needs_support", "Tôi cần hỗ trợ chăm sóc"
        RETURN_REQUEST = "return_request", "Tôi cần bàn giao lại cho tổ chức"
        MISSING = "missing", "Pet đang bị thất lạc"

    class Wellbeing(models.TextChoices):
        GOOD = "good", "Khỏe mạnh, hòa nhập tốt"
        STABLE = "stable", "Ổn định nhưng còn cần thời gian"
        CONCERNING = "concerning", "Có dấu hiệu cần được tư vấn"
        URGENT = "urgent", "Đang có vấn đề khẩn cấp"

    placement = models.ForeignKey(
        AdoptionPlacement,
        on_delete=models.CASCADE,
        related_name="check_in_requests",
    )
    milestone_month = models.PositiveSmallIntegerField(choices=Milestone.choices)
    due_on = models.DateField(db_index=True)
    notification_sent_at = models.DateTimeField(null=True, blank=True)
    care_status = models.CharField(
        max_length=24,
        choices=CareStatus.choices,
        blank=True,
    )
    wellbeing = models.CharField(
        max_length=20,
        choices=Wellbeing.choices,
        blank=True,
    )
    care_summary = models.TextField(blank=True)
    health_changes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("due_on", "milestone_month")
        constraints = [
            models.UniqueConstraint(
                fields=("placement", "milestone_month"),
                name="unique_placement_followup_milestone",
            )
        ]

    def __str__(self):
        return f"{self.placement} · tháng {self.milestone_month}"

    @property
    def is_completed(self):
        return self.submitted_at is not None


class AdoptionFollowUp(models.Model):
    class ContactMethod(models.TextChoices):
        PHONE = "phone", "Điện thoại"
        VIDEO = "video", "Gọi video"
        HOME_VISIT = "home_visit", "Thăm tại nhà"
        MESSAGE = "message", "Tin nhắn"
        OTHER = "other", "Khác"

    class Outcome(models.TextChoices):
        WELL = "well", "Đang được chăm sóc tốt"
        NEEDS_ATTENTION = "needs_attention", "Cần hỗ trợ thêm"
        UNREACHABLE = "unreachable", "Không liên lạc được"
        SUSPECTED_RESALE = "suspected_resale", "Nghi ngờ mua bán/chuyển nhượng"
        RETURNED = "returned", "Đã bàn giao lại tổ chức"

    placement = models.ForeignKey(
        AdoptionPlacement,
        on_delete=models.CASCADE,
        related_name="follow_ups",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="recorded_adoption_follow_ups",
        null=True,
        blank=True,
    )
    contact_method = models.CharField(max_length=20, choices=ContactMethod.choices)
    outcome = models.CharField(max_length=24, choices=Outcome.choices)
    notes = models.TextField()
    contacted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-contacted_at",)

    def __str__(self):
        return f"Theo dõi {self.placement} - {self.get_outcome_display()}"


class AdoptionSafetyReport(models.Model):
    class Reason(models.TextChoices):
        SALE_LISTING = "sale_listing", "Phát hiện rao bán"
        UNAUTHORIZED_TRANSFER = "unauthorized_transfer", "Tự ý chuyển cho người khác"
        NEGLECT = "neglect", "Có dấu hiệu bỏ bê/ngược đãi"
        LOST_CONTACT = "lost_contact", "Không thể liên lạc người nhận nuôi"
        OTHER = "other", "Vấn đề khác"

    class Status(models.TextChoices):
        PENDING = "pending", "Chờ xác minh"
        REVIEWING = "reviewing", "Đang xác minh"
        CONFIRMED = "confirmed", "Đã xác nhận vi phạm"
        DISMISSED = "dismissed", "Không đủ căn cứ"

    animal = models.ForeignKey(
        AnimalProfile,
        on_delete=models.PROTECT,
        related_name="safety_reports",
    )
    placement = models.ForeignKey(
        AdoptionPlacement,
        on_delete=models.SET_NULL,
        related_name="safety_reports",
        null=True,
        blank=True,
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="submitted_adoption_safety_reports",
        null=True,
        blank=True,
    )
    reason = models.CharField(max_length=30, choices=Reason.choices)
    description = models.TextField()
    evidence_url = models.URLField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_adoption_safety_reports",
        null=True,
        blank=True,
    )
    review_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-submitted_at",)

    def __str__(self):
        return f"Báo cáo an toàn #{self.pk} - {self.animal}"


class AdoptionRestriction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="adoption_restrictions",
    )
    organization = models.ForeignKey(
        RescueOrganization,
        on_delete=models.CASCADE,
        related_name="adoption_restrictions",
        null=True,
        blank=True,
        help_text="Để trống nếu hạn chế áp dụng trên toàn hệ thống.",
    )
    source_report = models.ForeignKey(
        AdoptionSafetyReport,
        on_delete=models.SET_NULL,
        related_name="restrictions",
        null=True,
        blank=True,
    )
    reason = models.TextField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_adoption_restrictions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "organization"),
                condition=models.Q(organization__isnull=False),
                name="unique_user_org_adoption_restriction",
            ),
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(organization__isnull=True),
                name="unique_global_adoption_restriction",
            ),
        ]

    def __str__(self):
        scope = self.organization or "Toàn hệ thống"
        return f"{self.user} - {scope}"
