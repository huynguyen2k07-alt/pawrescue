from django import forms
from django.contrib import admin

from .models import OrganizationMembership, RescueOrganization


class RescueOrganizationAdminForm(forms.ModelForm):
    class Meta:
        model = RescueOrganization
        fields = "__all__"
        labels = {
            "name": "Tên đơn vị", "description": "Ghi chú giới thiệu",
            "email": "Email liên hệ", "phone": "Số điện thoại",
            "address": "Địa chỉ", "is_verified": "Đã xác minh thông tin liên hệ",
            "is_active": "Đang tiếp nhận cứu hộ", "created_by": "Người tạo",
        }


@admin.register(RescueOrganization)
class RescueOrganizationAdmin(admin.ModelAdmin):
    form = RescueOrganizationAdminForm
    list_display = (
        "name",
        "email",
        "phone",
        "is_system",
        "is_verified",
        "is_active",
    )
    list_filter = ("is_system", "is_verified", "is_active")
    search_fields = ("name", "email", "phone", "address")
    autocomplete_fields = ("created_by",)
    readonly_fields = ("is_system", "created_at", "updated_at")
    inlines = ()
    fieldsets = (
        ("Liên hệ đơn vị", {"fields": ("name", "phone", "email", "address")}),
        ("Tiếp nhận yêu cầu", {"fields": ("is_verified", "is_active")}),
        ("Thông tin bổ sung", {"classes": ("collapse",), "fields": ("description", "created_by", "is_system", "created_at", "updated_at")}),
    )

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, extra_context={**(extra_context or {}), "title": "Đơn vị tiếp nhận"})

    def add_view(self, request, form_url="", extra_context=None):
        return super().add_view(request, form_url, {**(extra_context or {}), "title": "Thêm đơn vị tiếp nhận"})

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(request, object_id, form_url, {**(extra_context or {}), "title": "Thông tin đơn vị tiếp nhận"})

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.is_system:
            return fields + ("name", "created_by", "is_verified", "is_active")
        return fields

    def get_inline_instances(self, request, obj=None):
        if obj and obj.is_system:
            return []
        return super().get_inline_instances(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)

    def get_deleted_objects(self, objs, request):
        deleted, counts, permissions, protected = super().get_deleted_objects(
            objs, request
        )
        protected.extend(str(obj) for obj in objs if obj.is_system)
        return deleted, counts, permissions, protected

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset.filter(is_system=False))


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active")
    search_fields = (
        "user__email",
        "user__full_name",
        "organization__name",
    )
    autocomplete_fields = ("user", "organization")
    readonly_fields = ("joined_at",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "organization":
            kwargs["queryset"] = RescueOrganization.objects.filter(is_system=False)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
