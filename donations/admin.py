from django.contrib import admin
from django.db import models as db_models

from .models import CampaignExpense, Donation, FundraisingCampaign
from .widgets import PrivateAdminFileWidget


PRIVATE_FILE_WIDGETS = {
    db_models.FileField: {"widget": PrivateAdminFileWidget},
}


class DonationInline(admin.TabularInline):
    model = Donation
    extra = 0
    readonly_fields = ("submitted_at", "confirmed_at")
    autocomplete_fields = ("donor", "confirmed_by")
    formfield_overrides = PRIVATE_FILE_WIDGETS


class CampaignExpenseInline(admin.TabularInline):
    model = CampaignExpense
    extra = 0
    readonly_fields = ("created_at",)
    autocomplete_fields = ("recorded_by",)
    formfield_overrides = PRIVATE_FILE_WIDGETS


@admin.register(FundraisingCampaign)
class FundraisingCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "organization",
        "target_amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "organization", "created_at")
    search_fields = ("title", "description", "organization__name")
    autocomplete_fields = ("organization", "rescue_case", "created_by")
    readonly_fields = ("created_at", "updated_at")
    inlines = (DonationInline, CampaignExpenseInline)


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    formfield_overrides = PRIVATE_FILE_WIDGETS
    list_display = (
        "donor_name",
        "campaign",
        "amount",
        "status",
        "submitted_at",
    )
    list_filter = ("status", "method", "submitted_at")
    search_fields = (
        "donor_name",
        "donor_email",
        "reference_code",
        "campaign__title",
    )
    autocomplete_fields = ("campaign", "donor", "confirmed_by")
    readonly_fields = ("submitted_at", "confirmed_at")


@admin.register(CampaignExpense)
class CampaignExpenseAdmin(admin.ModelAdmin):
    formfield_overrides = PRIVATE_FILE_WIDGETS
    list_display = ("campaign", "category", "amount", "spent_at")
    list_filter = ("category", "spent_at", "is_receipt_public")
    search_fields = ("campaign__title", "description")
    autocomplete_fields = ("campaign", "recorded_by")
    readonly_fields = ("created_at",)
