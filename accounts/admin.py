from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.db.models import Q

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    permission_fields = ("role", "is_staff", "is_superuser", "groups", "user_permissions")
    ordering = ("email",)
    list_display = (
        "email",
        "full_name",
        "phone",
        "role",
        "is_staff",
        "is_active",
    )
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "full_name", "phone")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal information", {"fields": ("full_name", "phone", "role")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "full_name",
                    "phone",
                    "role",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        # Chỉ admin chính được tạo/cấp quyền quản trị; POST tự sửa vai trò hay quyền đều bị bỏ qua.
        fields = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:
            fields += self.permission_fields
        return fields

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return queryset.filter(
            Q(pk=request.user.pk)
            | Q(is_staff=False, is_superuser=False, role=User.Role.MEMBER)
        )


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin):
    """Chỉ quản trị viên cao nhất được phân quyền sử dụng các chức năng."""

    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)
