from django.contrib import admin

from .models import OrganizationMembership, RescueOrganization


class OrganizationMembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(RescueOrganization)
class RescueOrganizationAdmin(admin.ModelAdmin):
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
    inlines = (OrganizationMembershipInline,)


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
