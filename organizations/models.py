from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


SYSTEM_ORGANIZATION_NAME = "PawRescue"


def normalize_organization_name(value):
    return " ".join((value or "").split())


def is_reserved_organization_name(value):
    return normalize_organization_name(value).casefold() == (
        SYSTEM_ORGANIZATION_NAME.casefold()
    )


class RescueOrganization(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_rescue_organizations",
        null=True,
        blank=True,
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="OrganizationMembership",
        related_name="rescue_organizations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("is_system",),
                condition=models.Q(is_system=True),
                name="single_system_rescue_organization",
            ),
            models.CheckConstraint(
                condition=models.Q(is_system=False)
                | models.Q(name=SYSTEM_ORGANIZATION_NAME),
                name="system_rescue_organization_has_reserved_name",
            ),
            models.CheckConstraint(
                condition=models.Q(is_system=True)
                | ~models.Q(name__iexact=SYSTEM_ORGANIZATION_NAME),
                name="reserved_name_belongs_to_system_organization",
            ),
            models.CheckConstraint(
                condition=models.Q(is_system=False)
                | models.Q(
                    is_verified=True,
                    is_active=True,
                    created_by__isnull=True,
                ),
                name="system_rescue_organization_is_operational",
            ),
        ]

    def clean(self):
        super().clean()
        self.name = normalize_organization_name(self.name)
        if self.is_system and self.name != SYSTEM_ORGANIZATION_NAME:
            raise ValidationError(
                {"name": "Tổ chức hệ thống phải sử dụng tên PawRescue."}
            )
        if self.is_system and (
            not self.is_verified
            or not self.is_active
            or self.created_by_id is not None
        ):
            raise ValidationError(
                "Tổ chức hệ thống phải hoạt động, được xác minh và không thuộc sở hữu cá nhân."
            )
        if not self.is_system and is_reserved_organization_name(self.name):
            raise ValidationError(
                {"name": "Tên PawRescue được dành riêng cho hệ thống."}
            )

    def save(self, *args, **kwargs):
        self.name = normalize_organization_name(self.name)
        if (
            self.pk
            and not self.is_system
            and self.__class__.objects.filter(pk=self.pk, is_system=True).exists()
        ):
            raise ValidationError(
                {"is_system": "Không thể gỡ định danh tổ chức hệ thống."}
            )
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Chủ tổ chức"
        MANAGER = "manager", "Điều phối viên"
        VOLUNTEER = "volunteer", "Tình nguyện viên"

    organization = models.ForeignKey(
        RescueOrganization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VOLUNTEER,
    )
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("organization__name", "user__email")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "user"),
                name="unique_organization_membership",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.organization} ({self.get_role_display()})"

    def clean(self):
        super().clean()
        if self.organization_id and RescueOrganization.objects.filter(
            pk=self.organization_id,
            is_system=True,
        ).exists():
            raise ValidationError(
                {"organization": "Tổ chức hệ thống không có thành viên sở hữu."}
            )

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)
