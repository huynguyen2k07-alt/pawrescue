from django.contrib import admin
from django.db import models as db_models
from django.urls import reverse
from django.utils.html import format_html

from .forms import (
    AdminCampaignExpenseForm,
    AdminDonationForm,
    AdminFundraisingCampaignForm,
)
from .models import CampaignExpense, Donation, FundraisingCampaign
from .services import save_reviewed_donation
from .widgets import PrivateAdminFileWidget


PRIVATE_FILE_WIDGETS = {
    db_models.FileField: {"widget": PrivateAdminFileWidget},
}


class DonationProofLinkMixin:
    @admin.display(description="Chứng từ đóng góp")
    def proof_link(self, obj):
        if not obj or not obj.pk or not obj.proof:
            return "Chưa có chứng từ"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Xem chứng từ</a>',
            reverse("donations:donation-proof", args=(obj.pk,)),
        )


class ExpenseReceiptLinkMixin:
    @admin.display(description="Biên lai khoản chi")
    def receipt_link(self, obj):
        if not obj or not obj.pk or not obj.receipt:
            return "Chưa có biên lai"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Xem biên lai</a>',
            reverse("donations:expense-receipt", args=(obj.pk,)),
        )


class DonationInline(DonationProofLinkMixin, admin.TabularInline):
    model = Donation
    form = AdminDonationForm
    extra = 0
    readonly_fields = ("submitted_at", "confirmed_by", "confirmed_at", "proof_link")
    autocomplete_fields = ("donor",)
    formfield_overrides = PRIVATE_FILE_WIDGETS


class CampaignExpenseInline(ExpenseReceiptLinkMixin, admin.TabularInline):
    model = CampaignExpense
    form = AdminCampaignExpenseForm
    extra = 0
    readonly_fields = ("created_at", "receipt_link")
    autocomplete_fields = ("recorded_by",)
    formfield_overrides = PRIVATE_FILE_WIDGETS


@admin.register(FundraisingCampaign)
class FundraisingCampaignAdmin(admin.ModelAdmin):
    form = AdminFundraisingCampaignForm
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

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            if isinstance(obj, Donation):
                save_reviewed_donation(obj, reviewer=request.user)
            else:
                if isinstance(obj, CampaignExpense) and not obj.recorded_by_id:
                    obj.recorded_by = request.user
                obj.save()
        formset.save_m2m()


@admin.register(Donation)
class DonationAdmin(DonationProofLinkMixin, admin.ModelAdmin):
    form = AdminDonationForm
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
    autocomplete_fields = ("campaign", "donor")
    readonly_fields = ("submitted_at", "confirmed_by", "confirmed_at", "proof_link")

    def save_model(self, request, obj, form, change):
        save_reviewed_donation(obj, reviewer=request.user)


@admin.register(CampaignExpense)
class CampaignExpenseAdmin(ExpenseReceiptLinkMixin, admin.ModelAdmin):
    form = AdminCampaignExpenseForm
    formfield_overrides = PRIVATE_FILE_WIDGETS
    list_display = ("campaign", "category", "amount", "spent_at")
    list_filter = ("category", "spent_at", "is_receipt_public")
    search_fields = ("campaign__title", "description")
    autocomplete_fields = ("campaign", "recorded_by")
    readonly_fields = ("created_at", "receipt_link")

    def save_model(self, request, obj, form, change):
        if not obj.recorded_by_id:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)
