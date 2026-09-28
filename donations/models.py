from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import Sum

from organizations.models import RescueOrganization
from rescue.models import RescueCase
from rescue.uploads import sanitize_model_image

from .storage import private_donation_storage
from .uploads import sanitize_model_receipt


class FundraisingCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Bản nháp"
        ACTIVE = "active", "Đang gây quỹ"
        COMPLETED = "completed", "Đã đạt mục tiêu"
        CLOSED = "closed", "Đã đóng"

    organization = models.ForeignKey(
        RescueOrganization,
        on_delete=models.CASCADE,
        related_name="fundraising_campaigns",
    )
    rescue_case = models.ForeignKey(
        RescueCase,
        on_delete=models.SET_NULL,
        related_name="fundraising_campaigns",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_fundraising_campaigns",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    target_amount = models.DecimalField(
        max_digits=14,
        decimal_places=0,
        validators=(MinValueValidator(Decimal("1")),),
    )
    cover_image = models.FileField(
        upload_to="fundraising_campaigns/%Y/%m/",
        blank=True,
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            ),
        ),
    )
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_name = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=60, blank=True)
    transfer_content = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    starts_at = models.DateField(null=True, blank=True)
    ends_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        sanitize_model_image(self, "cover_image")
        return super().save(*args, **kwargs)

    @property
    def confirmed_amount(self):
        annotated = getattr(self, "confirmed_total", None)
        if annotated is not None:
            return annotated
        return self.donations.filter(
            status=Donation.Status.CONFIRMED
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    @property
    def expense_amount(self):
        annotated = getattr(self, "expense_total", None)
        if annotated is not None:
            return annotated
        return self.expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    @property
    def balance_amount(self):
        return self.confirmed_amount - self.expense_amount

    @property
    def progress_percent(self):
        if not self.target_amount:
            return 0
        return min(int(self.confirmed_amount * 100 / self.target_amount), 100)


class Donation(models.Model):
    class Method(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Chuyển khoản"
        CASH = "cash", "Tiền mặt"
        OTHER = "other", "Khác"

    class Status(models.TextChoices):
        PENDING = "pending", "Chờ xác nhận"
        CONFIRMED = "confirmed", "Đã xác nhận"
        REJECTED = "rejected", "Không hợp lệ"

    campaign = models.ForeignKey(
        FundraisingCampaign,
        on_delete=models.CASCADE,
        related_name="donations",
    )
    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="donations",
        null=True,
        blank=True,
    )
    donor_name = models.CharField(max_length=150)
    donor_email = models.EmailField()
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=0,
        validators=(MinValueValidator(Decimal("1")),),
    )
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.BANK_TRANSFER,
    )
    reference_code = models.CharField(max_length=120, blank=True)
    proof = models.FileField(
        storage=private_donation_storage,
        upload_to="donation_proofs/%Y/%m/",
        blank=True,
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp", "pdf")
            ),
        ),
    )
    message = models.TextField(blank=True)
    is_anonymous = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="confirmed_donations",
        null=True,
        blank=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-submitted_at",)

    def __str__(self):
        return f"{self.donor_name} - {self.amount} - {self.campaign}"

    def save(self, *args, **kwargs):
        sanitize_model_receipt(self, "proof")
        return super().save(*args, **kwargs)


class CampaignExpense(models.Model):
    class Category(models.TextChoices):
        MEDICAL = "medical", "Khám chữa bệnh"
        MEDICINE = "medicine", "Thuốc và vật tư y tế"
        FOOD = "food", "Thức ăn"
        TRANSPORT = "transport", "Vận chuyển"
        SHELTER = "shelter", "Lưu trú"
        EQUIPMENT = "equipment", "Thiết bị"
        OTHER = "other", "Khác"

    campaign = models.ForeignKey(
        FundraisingCampaign,
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=0,
        validators=(MinValueValidator(Decimal("1")),),
    )
    description = models.TextField()
    spent_at = models.DateField()
    receipt = models.FileField(
        storage=private_donation_storage,
        upload_to="campaign_receipts/%Y/%m/",
        blank=True,
        validators=(
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp", "pdf")
            ),
        ),
    )
    is_receipt_public = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="recorded_campaign_expenses",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-spent_at", "-created_at")

    def __str__(self):
        return f"{self.get_category_display()} - {self.amount}"

    def save(self, *args, **kwargs):
        sanitize_model_receipt(self, "receipt")
        return super().save(*args, **kwargs)
