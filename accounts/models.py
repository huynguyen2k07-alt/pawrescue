from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = "member", "Người dùng"
        COLLABORATOR = "collaborator", "Cộng tác viên hỗ trợ"

    username = None

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    @property
    def is_collaborator(self):
        return self.role == self.Role.COLLABORATOR

    def __str__(self):
        return self.email
