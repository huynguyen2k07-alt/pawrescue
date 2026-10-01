from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import (
    AdoptionApplication,
    AdoptionCheckInRequest,
    AdoptionFollowUp,
    AdoptionPlacement,
    AdoptionRestriction,
    AdoptionSafetyReport,
    AnimalProfile,
    AnimalProfileImage,
)


class AnimalProfileImageInline(admin.TabularInline):
    model = AnimalProfileImage
    extra = 1
    readonly_fields = ("uploaded_at",)


@admin.register(AnimalProfile)
class AnimalProfileAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "animal_type",
        "organization",
        "status",
        "application_count",
        "published_at",
    )
    list_filter = ("status", "animal_type", "age_group", "sex", "organization")
    search_fields = ("name", "breed", "location", "description")
    autocomplete_fields = ("organization", "rescue_case", "created_by")
    readonly_fields = ("published_at", "updated_at", "adopted_at")
    inlines = (AnimalProfileImageInline,)
    list_per_page = 30
    save_on_top = True
    view_on_site = True

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_application_count=Count("applications"))

    @admin.display(description="Số đơn", ordering="_application_count")
    def application_count(self, obj):
        return obj._application_count


@admin.register(AnimalProfileImage)
class AnimalProfileImageAdmin(admin.ModelAdmin):
    list_display = ("animal", "caption", "uploaded_at")
    search_fields = ("animal__name", "caption")
    autocomplete_fields = ("animal",)
    readonly_fields = ("uploaded_at",)


@admin.register(AdoptionApplication)
class AdoptionApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "applicant_name",
        "animal",
        "status_badge",
        "pledge_badge",
        "submitted_at",
        "reviewed_at",
    )
    list_filter = ("status", "housing_type", "submitted_at")
    search_fields = (
        "applicant_name",
        "phone",
        "applicant__email",
        "animal__name",
    )
    autocomplete_fields = ("animal", "applicant", "reviewer")
    readonly_fields = (
        "submitted_at",
        "reviewed_at",
        "pledge_accepted_at",
        "identity_verified_at",
    )
    list_select_related = ("animal", "applicant", "animal__organization")
    list_per_page = 30
    date_hierarchy = "submitted_at"

    @admin.display(description="Trạng thái", ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span class="paw-admin-status paw-admin-status-{}">{}</span>',
            obj.status,
            obj.get_status_display(),
        )

    @admin.display(description="Cam kết", boolean=True)
    def pledge_badge(self, obj):
        return obj.has_safety_pledge


class AdoptionFollowUpInline(admin.TabularInline):
    model = AdoptionFollowUp
    extra = 0
    readonly_fields = ("created_at",)


class AdoptionCheckInRequestInline(admin.TabularInline):
    model = AdoptionCheckInRequest
    extra = 0
    fields = (
        "milestone_month",
        "due_on",
        "notification_sent_at",
        "care_status",
        "wellbeing",
        "submitted_at",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AdoptionPlacement)
class AdoptionPlacementAdmin(admin.ModelAdmin):
    list_display = (
        "animal",
        "adopter",
        "organization",
        "status",
        "next_follow_up_on",
        "is_active",
    )
    list_filter = ("status", "is_active", "organization")
    search_fields = ("animal__name", "adopter__email", "adopter__full_name")
    autocomplete_fields = ("application", "animal", "adopter", "organization")
    readonly_fields = ("created_at", "updated_at")
    inlines = (AdoptionCheckInRequestInline, AdoptionFollowUpInline)
    list_select_related = ("animal", "adopter", "organization", "application")
    list_per_page = 30


@admin.register(AdoptionFollowUp)
class AdoptionFollowUpAdmin(admin.ModelAdmin):
    list_display = ("placement", "outcome", "contact_method", "contacted_at")
    list_filter = ("outcome", "contact_method")
    autocomplete_fields = ("placement", "created_by")
    readonly_fields = ("created_at",)


@admin.register(AdoptionCheckInRequest)
class AdoptionCheckInRequestAdmin(admin.ModelAdmin):
    list_display = (
        "placement",
        "milestone_month",
        "due_on",
        "notification_sent_at",
        "wellbeing",
        "submitted_at",
    )
    list_filter = ("milestone_month", "care_status", "wellbeing", "due_on")
    search_fields = (
        "placement__animal__name",
        "placement__adopter__email",
        "placement__adopter__full_name",
    )
    autocomplete_fields = ("placement",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "notification_sent_at",
        "submitted_at",
    )
    list_select_related = ("placement__animal", "placement__adopter")


@admin.register(AdoptionSafetyReport)
class AdoptionSafetyReportAdmin(admin.ModelAdmin):
    list_display = (
        "animal",
        "reason",
        "status_badge",
        "reporter",
        "submitted_at",
    )
    list_filter = ("status", "reason", "submitted_at")
    search_fields = ("animal__name", "description", "reporter__email")
    autocomplete_fields = ("animal", "placement", "reporter", "reviewed_by")
    readonly_fields = ("submitted_at", "reviewed_at")
    list_select_related = ("animal", "reporter", "reviewed_by")
    list_per_page = 30
    date_hierarchy = "submitted_at"

    @admin.display(description="Trạng thái", ordering="status")
    def status_badge(self, obj):
        return format_html(
            '<span class="paw-admin-status paw-admin-status-{}">{}</span>',
            obj.status,
            obj.get_status_display(),
        )


@admin.register(AdoptionRestriction)
class AdoptionRestrictionAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "is_active", "updated_at")
    list_filter = ("is_active", "organization")
    search_fields = ("user__email", "user__full_name", "reason")
    autocomplete_fields = ("user", "organization", "source_report", "created_by")
    readonly_fields = ("created_at", "updated_at")
