from django.contrib import admin

from .models import CampaignExpense, Donation, FundraisingCampaign


class DonationInline(admin.TabularInline):
    model = Donation
    extra = 0
    readonly_fields = ("submitted_at", "confirmed_at")
    autocomplete_fields = ("donor", "confirmed_by")


class CampaignExpenseInline(admin.TabularInline):
    model = CampaignExpense
    extra = 0
    readonly_fields = ("created_at",)
    autocomplete_fields = ("recorded_by",)


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
    list_display = ("campaign", "category", "amount", "spent_at")
    list_filter = ("category", "spent_at", "is_receipt_public")
    search_fields = ("campaign__title", "description")
    autocomplete_fields = ("campaign", "recorded_by")
    readonly_fields = ("created_at",)
