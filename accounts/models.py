from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = "member", "Người dùng"
        COLLABORATOR = "collaborator", "Nhân viên hỗ trợ"
        MODERATOR = "moderator", "Cộng tác viên cứu hộ"

    username = None

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(
        verbose_name="Vai trò",
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
        help_text=(
            "Admin chính cấp vai trò. Cộng tác viên cứu hộ (cá nhân hoặc trung tâm) "
            "chỉ xử lý ca được giao; nhân viên hỗ trợ sử dụng hộp thư hỗ trợ. "
            "Quyền admin được quản lý riêng tại phần Phân quyền."
        ),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    @property
    def is_collaborator(self):
        return self.role == self.Role.COLLABORATOR

    @property
    def is_moderator(self):
        return self.role == self.Role.MODERATOR

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name.strip() or self.email

    def get_short_name(self):
        return self.get_full_name()
