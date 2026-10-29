from urllib.parse import urlencode

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models as db_models
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from support.models import SupportConversation

from .models import (
    CaseStatusHistory,
    CommunityFeedback,
    ContributorProfile,
    KnowledgeArticle,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseImage,
    RescueUpdate,
    RescueUpdateImage,
)
from .notifications import case_participant_ids, create_case_notifications
from .forms import CaseStatusUpdateForm
from .geography import is_within_da_nang
from .permissions import is_rescue_admin
from .services import system_rescue_organization as _pawrescue_organization
from .uploads import sanitize_image_upload
from .widgets import PrivateAdminImageWidget


TERMINAL_CASE_STATUSES = {
    RescueCase.Status.RESCUED,
    RescueCase.Status.CLOSED,
    RescueCase.Status.CANCELLED,
}


class ValidatedAdminImageForm(forms.ModelForm):
    """Hiển thị lỗi tải ảnh ngay trên biểu mẫu trước khi lưu tệp."""

    def clean(self):
        cleaned_data = super().clean()
        for field in self._meta.model._meta.fields:
            if not isinstance(field, db_models.FileField):
                continue
            uploaded_file = cleaned_data.get(field.name)
            if not uploaded_file or getattr(uploaded_file, "_committed", False):
                continue
            try:
                if uploaded_file.size > 5 * 1024 * 1024:
                    raise forms.ValidationError("Mỗi ảnh phải nhỏ hơn 5 MB.")
                cleaned_data[field.name] = sanitize_image_upload(uploaded_file)
            except forms.ValidationError as error:
                self.add_error(field.name, error)
        return cleaned_data


class RescueCaseAdminForm(ValidatedAdminImageForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "title": "Tiêu đề yêu cầu", "description": "Nội dung báo tin",
            "animal_type": "Loài động vật", "animal_details": "Đặc điểm nhận dạng",
            "urgency": "Mức độ khẩn cấp", "reporter": "Người báo tin",
            "organization": "Đơn vị xử lý", "contact_name": "Tên liên hệ",
            "contact_phone": "Số điện thoại", "address": "Địa chỉ hiện trường",
            "latitude": "Vĩ độ", "longitude": "Kinh độ",
            "is_location_private": "Bảo vệ vị trí chính xác",
        }
        for name, field in self.fields.items():
            field.label = labels.get(name, field.label)

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")
        location_changed = bool({"latitude", "longitude"} & set(self.changed_data))
        if self.instance._state.adding or location_changed or latitude is not None or longitude is not None:
            if latitude is None or longitude is None:
                message = "Hãy chọn đầy đủ vị trí bằng cách đặt ghim trên bản đồ."
                if latitude is None and "latitude" not in self.errors:
                    self.add_error("latitude", message)
                if longitude is None and "longitude" not in self.errors:
                    self.add_error("longitude", message)
            elif not is_within_da_nang(latitude, longitude):
                message = "PawRescue hiện chỉ tiếp nhận ca trong phạm vi Đà Nẵng."
                self.add_error("latitude", message)
                self.add_error("longitude", message)
        return cleaned_data


def _feedback_gmail_url(feedback):
    subject = f"PawRescue phản hồi góp ý #{feedback.pk}"
    body = (
        f"Chào {feedback.name},\n\n"
        "Cảm ơn bạn đã gửi góp ý cho PawRescue về "
        f'“{feedback.get_category_display()}”.\n\n'
        "PawRescue phản hồi:\n\n\n"
        "---\n"
        f"Góp ý của bạn: {feedback.message}\n\n"
        "Trân trọng,\nĐội ngũ PawRescue"
    )
    return "https://mail.google.com/mail/?" + urlencode(
        {
            "view": "cm",
            "fs": "1",
            "to": feedback.email,
            "su": subject,
            "body": body,
        }
    )


def _accept_case(case, organization, actor):
    if (
        case.organization_id is not None
        or case.status in TERMINAL_CASE_STATUSES
    ):
        return False

    previous_status = case.status
    case.organization = organization
    if case.status == RescueCase.Status.REPORTED:
        case.status = RescueCase.Status.VERIFIED
    case.save(update_fields=("organization", "status", "updated_at"))

    if previous_status != case.status:
        CaseStatusHistory.objects.create(
            rescue_case=case,
            from_status=previous_status,
            to_status=case.status,
            changed_by=actor,
            note="PawRescue đã tiếp nhận và xác minh tin báo.",
        )
    create_case_notifications(
        recipient_ids=(case.reporter_id,),
        rescue_case=case,
        kind=Notification.Kind.CASE_CLAIMED,
        title="Ca cứu hộ đã được PawRescue tiếp nhận",
        message=(
            f'PawRescue đã tiếp nhận ca "{case.title}" và đang điều phối xử lý.'
        ),
        actor=actor,
    )
    return True


class PrivateRescueImagePreviewMixin:
    @admin.display(description="Ảnh hiện trường")
    def image_preview(self, obj):
        if not obj or not obj.pk or not obj.image:
            return "Chưa có ảnh."
        route = "rescue:case-image" if isinstance(obj, RescueCaseImage) else "rescue:update-image"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">Xem ảnh</a>',
            reverse(route, args=(obj.pk,)),
        )


class RescueCaseImageInline(PrivateRescueImagePreviewMixin, admin.TabularInline):
    model = RescueCaseImage
    form = ValidatedAdminImageForm
    extra = 1
    autocomplete_fields = ("uploaded_by",)
    readonly_fields = ("image_preview", "uploaded_at")
    formfield_overrides = {
        db_models.FileField: {"widget": PrivateAdminImageWidget},
    }


class RescueAdminOnlyMixin:
    def has_module_permission(self, request):
        return is_rescue_admin(request.user)

    def has_view_permission(self, request, obj=None):
        return is_rescue_admin(request.user)

    def has_add_permission(self, request):
        return is_rescue_admin(request.user)

    def has_change_permission(self, request, obj=None):
        return is_rescue_admin(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_rescue_admin(request.user)


@admin.register(RescueCase)
class RescueCaseAdmin(RescueAdminOnlyMixin, admin.ModelAdmin):
    form = RescueCaseAdminForm
    change_form_template = "admin/rescue/rescuecase/change_form.html"
    change_list_template = "admin/rescue/rescuecase/change_list.html"
    list_display = (
        "id",
        "title",
        "animal_type",
        "urgency",
        "status",
        "organization",
        "reported_at",
    )
    list_display_links = ("id", "title")
    list_filter = ("status", "organization")
    search_fields = (
        "title",
        "description",
        "address",
        "contact_name",
        "contact_phone",
    )
    autocomplete_fields = ("reporter", "organization")
    readonly_fields = ("status", "reported_at", "updated_at", "closed_at")
    actions = ("accept_selected_cases",)
    save_on_top = False
    view_on_site = True
    inlines = (RescueCaseImageInline,)
    fieldsets = (
        ("Thông tin yêu cầu", {"fields": ("title", "description", ("animal_type", "urgency"), "animal_details")}),
        ("Hiện trường và liên hệ", {"fields": ("address", ("latitude", "longitude"), "is_location_private", ("contact_name", "contact_phone"))}),
        ("Thông tin tiếp nhận", {"classes": ("collapse",), "fields": ("reporter", "organization")}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return fields + ("reporter", "organization") if obj else fields

    def get_view_on_site_url(self, obj=None):
        if obj is None or obj.pk is None:
            return None
        return reverse("rescue:case-detail", args=(obj.pk,))

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/quick-status/<str:status>/",
                self.admin_site.admin_view(self.quick_status_view),
                name="rescue_rescuecase_quick_status",
            ),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        if request.GET.get("status__exact") == "":
            request.GET = request.GET.copy()
            request.GET.pop("status__exact", None)
        active_statuses = (
            RescueCase.Status.REPORTED,
            RescueCase.Status.VERIFIED,
            RescueCase.Status.ASSIGNED,
            RescueCase.Status.IN_PROGRESS,
        )
        cases = RescueCase.objects.select_related("organization", "reporter")
        counts = cases.aggregate(
            active=Count("id", filter=Q(status__in=active_statuses)),
            rescued=Count("id", filter=Q(status=RescueCase.Status.RESCUED)),
            cancelled=Count("id", filter=Q(status=RescueCase.Status.CANCELLED)),
        )
        extra_context = {
            **(extra_context or {}),
            "title": "Yêu cầu cứu hộ",
            "case_status_choices": RescueCase.Status.choices,
            "selected_case_status": request.GET.get("status__exact", ""),
            "has_delete_permission": self.has_delete_permission(request),
            "workflow_cases": cases.filter(status__in=active_statuses)[:12],
            "rescued_cases": cases.filter(status=RescueCase.Status.RESCUED)[:8],
            "rescue_counts": counts,
            "all_rescued_url": (
                reverse("admin:rescue_rescuecase_changelist")
                + "?status__exact=rescued"
            ),
        }
        return super().changelist_view(request, extra_context=extra_context)

    def quick_status_view(self, request, object_id, status):
        if request.method != "POST":
            return HttpResponseNotAllowed(("POST",))
        rescue_case = self.get_object(request, object_id)
        if rescue_case is None:
            raise Http404
        if not self.has_change_permission(request, rescue_case):
            raise PermissionDenied

        allowed_statuses = {
            RescueCase.Status.VERIFIED: (
                "Đã xác nhận ca cứu hộ.",
                "Quản trị viên đã xác minh thông tin.",
            ),
            RescueCase.Status.RESCUED: (
                "Đã ghi nhận giải cứu thành công.",
                "Đội cứu hộ xác nhận động vật đã được giải cứu an toàn.",
            ),
            RescueCase.Status.CANCELLED: (
                "Đã hủy ca cứu hộ.",
                "Quản trị viên đã hủy ca cứu hộ.",
            ),
            RescueCase.Status.CLOSED: ("Đã đánh giá và đóng ca cứu hộ.", ""),
        }
        if status not in allowed_statuses:
            raise Http404

        success_message, history_note = allowed_statuses[status]
        with transaction.atomic():
            rescue_case = RescueCase.objects.select_for_update().get(
                pk=rescue_case.pk
            )
            if rescue_case.status in TERMINAL_CASE_STATUSES:
                self.message_user(request, "Ca đã được chốt sổ, không thể đổi lại trạng thái.", level=messages.INFO)
                return HttpResponseRedirect(reverse("admin:rescue_rescuecase_changelist"))
            if status in TERMINAL_CASE_STATUSES:
                review_form = CaseStatusUpdateForm(
                    {"status": status, "note": request.POST.get("note", "")},
                    current_status=rescue_case.status,
                )
                if not review_form.is_valid():
                    self.message_user(request, "Hãy ghi đánh giá kết quả trước khi chốt ca.", level=messages.WARNING)
                    return HttpResponseRedirect(
                        reverse("rescue:case-detail", args=(rescue_case.pk,))
                        + f"?review={status}#case-review"
                    )
                history_note = review_form.cleaned_data["note"]
            if (
                status in {RescueCase.Status.VERIFIED, RescueCase.Status.RESCUED}
                and rescue_case.organization_id is None
            ):
                rescue_case.organization = _pawrescue_organization(request.user)
                rescue_case.save(update_fields=("organization", "updated_at"))
            history = rescue_case.change_status(
                status,
                changed_by=request.user,
                note=history_note,
            )
            if history is not None:
                create_case_notifications(
                    recipient_ids=case_participant_ids(rescue_case),
                    rescue_case=rescue_case,
                    kind=Notification.Kind.STATUS_CHANGED,
                    title="Trạng thái ca cứu hộ đã thay đổi",
                    message=(
                        f'Ca "{rescue_case.title}" đã chuyển sang trạng thái '
                        f'“{rescue_case.get_status_display()}”.'
                    ),
                    actor=request.user,
                )

        if history is None:
            self.message_user(
                request,
                "Ca cứu hộ đã ở trạng thái này rồi.",
                level=messages.INFO,
            )
        else:
            self.message_user(request, success_message, level=messages.SUCCESS)
        return HttpResponseRedirect(reverse("admin:rescue_rescuecase_changelist"))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        rescue_case = self.get_object(request, object_id)
        if rescue_case is None:
            raise Http404
        if not self.has_change_permission(request, rescue_case):
            raise PermissionDenied
        if request.method == "GET" and request.GET.get("edit") != "1":
            return HttpResponseRedirect(reverse("rescue:case-detail", args=(rescue_case.pk,)))
        extra_context = {
            **(extra_context or {}),
            "title": "Sửa thông tin yêu cầu",
            "subtitle": rescue_case.title,
            "accept_case_available": bool(
                rescue_case
                and rescue_case.organization_id is None
                and rescue_case.status not in TERMINAL_CASE_STATUSES
            ),
        }
        return super().change_view(
            request,
            object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

    @admin.action(description="Tiếp nhận các ca đã chọn bởi PawRescue")
    def accept_selected_cases(self, request, queryset):
        accepted_count = 0
        organization = _pawrescue_organization(request.user)
        with transaction.atomic():
            for rescue_case in queryset.select_for_update():
                if _accept_case(rescue_case, organization, request.user):
                    accepted_count += 1

        skipped_count = queryset.count() - accepted_count
        if accepted_count:
            self.message_user(
                request,
                f"PawRescue đã tiếp nhận {accepted_count} ca cứu hộ.",
                level=messages.SUCCESS,
            )
        if skipped_count:
            self.message_user(
                request,
                f"Bỏ qua {skipped_count} ca đã có đơn vị tiếp nhận hoặc đã kết thúc.",
                level=messages.INFO,
            )

    def save_model(self, request, obj, form, change):
        previous_status = None
        previous_organization_id = None
        if change:
            previous_case = (
                RescueCase.objects.filter(pk=obj.pk)
                .values("status", "organization_id")
                .first()
            )
            if previous_case:
                previous_status = previous_case["status"]
                previous_organization_id = previous_case["organization_id"]

        accept_requested = bool(
            change
            and "_accept_case" in request.POST
            and previous_organization_id is None
            and previous_status not in TERMINAL_CASE_STATUSES
        )
        request._pawrescue_accept_processed = accept_requested
        if accept_requested:
            obj.organization = _pawrescue_organization(request.user)
            if obj.status == RescueCase.Status.REPORTED:
                obj.status = RescueCase.Status.VERIFIED

        if obj.status in {
            RescueCase.Status.RESCUED,
            RescueCase.Status.CLOSED,
            RescueCase.Status.CANCELLED,
        }:
            obj.closed_at = obj.closed_at or timezone.now()
        else:
            obj.closed_at = None

        super().save_model(request, obj, form, change)

        if previous_status is not None and previous_status != obj.status:
            CaseStatusHistory.objects.create(
                rescue_case=obj,
                from_status=previous_status,
                to_status=obj.status,
                changed_by=request.user,
                note="Status changed in Django Admin.",
            )
            if not accept_requested:
                create_case_notifications(
                    recipient_ids=case_participant_ids(obj),
                    rescue_case=obj,
                    kind=Notification.Kind.STATUS_CHANGED,
                    title="Trạng thái ca cứu hộ đã thay đổi",
                    message=(
                        f'Ca "{obj.title}" đã chuyển sang trạng thái '
                        f'“{obj.get_status_display()}”.'
                    ),
                    actor=request.user,
                )

        if accept_requested:
            create_case_notifications(
                recipient_ids=(obj.reporter_id,),
                rescue_case=obj,
                kind=Notification.Kind.CASE_CLAIMED,
                title="Ca cứu hộ đã được PawRescue tiếp nhận",
                message=(
                    f'PawRescue đã tiếp nhận ca "{obj.title}" '
                    "và đang điều phối xử lý."
                ),
                actor=request.user,
            )

    def response_change(self, request, obj):
        if "_accept_case" in request.POST:
            if getattr(request, "_pawrescue_accept_processed", False):
                self.message_user(
                    request,
                    "Đã tiếp nhận ca bởi PawRescue. Người báo tin cũng đã được thông báo.",
                    level=messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    "Không thể tiếp nhận ca đã có đơn vị phụ trách hoặc đã kết thúc.",
                    level=messages.INFO,
                )
            return HttpResponseRedirect(reverse("rescue:case-detail", args=(obj.pk,)))
        if not any(name in request.POST for name in ("_continue", "_addanother", "_saveasnew")):
            self.message_user(request, "Đã lưu thay đổi của yêu cầu.", level=messages.SUCCESS)
            return HttpResponseRedirect(reverse("rescue:case-detail", args=(obj.pk,)))
        return super().response_change(request, obj)

    def response_add(self, request, obj, post_url_continue=None):
        if not any(name in request.POST for name in ("_continue", "_addanother", "_saveasnew")):
            self.message_user(request, "Đã tạo yêu cầu cứu hộ.", level=messages.SUCCESS)
            return HttpResponseRedirect(reverse("rescue:case-detail", args=(obj.pk,)))
        return super().response_add(request, obj, post_url_continue)


@admin.register(RescueCaseImage)
class RescueCaseImageAdmin(PrivateRescueImagePreviewMixin, RescueAdminOnlyMixin, admin.ModelAdmin):
    form = ValidatedAdminImageForm
    list_display = ("rescue_case", "caption", "uploaded_by", "uploaded_at")
    search_fields = ("rescue_case__title", "caption")
    autocomplete_fields = ("rescue_case", "uploaded_by")
    readonly_fields = ("image_preview", "uploaded_at")
    formfield_overrides = {
        db_models.FileField: {"widget": PrivateAdminImageWidget},
    }


@admin.register(RescueAssignment)
class RescueAssignmentAdmin(RescueAdminOnlyMixin, admin.ModelAdmin):
    list_display = ("rescue_case", "assignee", "is_active", "assigned_at")
    list_filter = ("is_active",)
    search_fields = (
        "rescue_case__title",
        "assignee__email",
        "assignee__full_name",
    )
    autocomplete_fields = ("rescue_case", "assignee", "assigned_by")
    readonly_fields = ("rescue_case", "workflow_link", "assignee", "assigned_by", "notes", "is_active", "assigned_at", "completed_at")

    @admin.display(description="Điều phối ca")
    def workflow_link(self, obj):
        return format_html(
            '<a href="{}">Mở ca để phân công hoặc gỡ phân công</a>',
            reverse("rescue:case-detail", args=(obj.rescue_case_id,)),
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        resolver_match = getattr(request, "resolver_match", None)
        return bool(
            is_rescue_admin(request.user)
            and resolver_match
            and resolver_match.url_name in {
                "rescue_rescuecase_delete",
                "rescue_rescuecase_changelist",
            }
        )


class RescueUpdateImageInline(PrivateRescueImagePreviewMixin, admin.TabularInline):
    model = RescueUpdateImage
    form = ValidatedAdminImageForm
    extra = 0
    fields = ("image_preview", "uploaded_at")
    readonly_fields = fields
    can_delete = False
    formfield_overrides = {
        db_models.FileField: {"widget": PrivateAdminImageWidget},
    }

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RescueUpdate)
class RescueUpdateAdmin(RescueAdminOnlyMixin, admin.ModelAdmin):
    list_display = ("rescue_case", "author", "created_at")
    search_fields = ("rescue_case__title", "author__email", "note")
    autocomplete_fields = ("rescue_case", "author")
    readonly_fields = ("created_at",)
    inlines = (RescueUpdateImageInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(RescueAdminOnlyMixin, admin.ModelAdmin):
    list_display = (
        "recipient",
        "kind",
        "rescue_case",
        "is_read",
        "created_at",
    )
    list_filter = ("kind", "is_read", "created_at")
    search_fields = (
        "recipient__email",
        "recipient__full_name",
        "title",
        "message",
        "rescue_case__title",
    )
    autocomplete_fields = ("recipient", "actor", "rescue_case")
    readonly_fields = ("created_at", "read_at")


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(admin.ModelAdmin):
    form = ValidatedAdminImageForm
    list_display = (
        "title",
        "category",
        "is_featured",
        "is_published",
        "published_at",
    )
    list_editable = ("is_featured", "is_published")
    list_filter = ("category", "is_featured", "is_published")
    search_fields = ("title", "excerpt", "body", "source_name")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    save_on_top = True
    view_on_site = True


@admin.register(ContributorProfile)
class ContributorProfileAdmin(admin.ModelAdmin):
    form = ValidatedAdminImageForm
    list_display = ("name", "role", "display_order", "is_active")
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "role", "bio")
    ordering = ("display_order", "name")
    readonly_fields = ("created_at", "updated_at")
    save_on_top = True
    view_on_site = True

    def get_view_on_site_url(self, obj=None):
        if obj is None or obj.pk is None:
            return None
        return reverse("rescue:team")


@admin.register(CommunityFeedback)
class CommunityFeedbackAdmin(RescueAdminOnlyMixin, admin.ModelAdmin):
    change_list_template = "admin/rescue/communityfeedback/change_list.html"
    change_form_template = "admin/rescue/communityfeedback/change_form.html"
    list_display = (
        "feedback_summary",
        "category",
        "status",
        "submitted_at",
        "contact_actions",
    )
    list_display_links = ("feedback_summary",)
    list_filter = ("status", "category", "submitted_at")
    search_fields = ("name", "email", "message")
    readonly_fields = (
        "user",
        "name",
        "email",
        "category",
        "message",
        "submitted_at",
        "reviewed_at",
    )
    fields = (
        "status",
        ("name", "email"),
        "user",
        "category",
        "message",
        ("submitted_at", "reviewed_at"),
    )

    @admin.display(description="Người gửi")
    def feedback_summary(self, obj):
        return format_html(
            "<strong>{}</strong><br><small>{}</small>",
            obj.name,
            obj.email,
        )

    @admin.display(description="Liên hệ")
    def contact_actions(self, obj):
        return format_html(
            '<a class="paw-feedback-table-action" href="{}" '
            'target="_blank" rel="noopener noreferrer">Gmail ↗</a>',
            _feedback_gmail_url(obj),
        )

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/quick-status/<str:status>/",
                self.admin_site.admin_view(self.quick_status_view),
                name="rescue_communityfeedback_quick_status",
            ),
            path(
                "<path:object_id>/open-chat/",
                self.admin_site.admin_view(self.open_chat_view),
                name="rescue_communityfeedback_open_chat",
            ),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        if not getattr(response, "context_data", None) or "cl" not in response.context_data:
            return response
        feedback_queryset = response.context_data["cl"].queryset.select_related("user")
        counts = feedback_queryset.aggregate(
            new=Count(
                "id",
                filter=Q(status=CommunityFeedback.Status.NEW),
            ),
            reviewed=Count(
                "id",
                filter=Q(status=CommunityFeedback.Status.REVIEWED),
            ),
            closed=Count(
                "id",
                filter=Q(status=CommunityFeedback.Status.CLOSED),
            ),
        )
        feedback_items = list(feedback_queryset[:20])
        for feedback in feedback_items:
            feedback.gmail_reply_url = _feedback_gmail_url(feedback)
        response.context_data.update({
            "feedback_counts": counts,
            "feedback_items": feedback_items,
        })
        return response

    def change_view(self, request, object_id, form_url="", extra_context=None):
        feedback = self.get_object(request, object_id)
        if (
            request.method == "GET"
            and feedback is not None
            and feedback.status == CommunityFeedback.Status.NEW
            and self.has_change_permission(request, feedback)
        ):
            feedback.status = CommunityFeedback.Status.REVIEWED
            feedback.reviewed_at = timezone.now()
            feedback.save(update_fields=("status", "reviewed_at"))

        extra_context = {
            **(extra_context or {}),
            "gmail_reply_url": (
                _feedback_gmail_url(feedback) if feedback is not None else ""
            ),
        }
        return super().change_view(
            request,
            object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

    def quick_status_view(self, request, object_id, status):
        if request.method != "POST":
            return HttpResponseNotAllowed(("POST",))
        feedback = self.get_object(request, object_id)
        if feedback is None:
            raise Http404
        if not self.has_change_permission(request, feedback):
            raise PermissionDenied

        allowed_statuses = {
            CommunityFeedback.Status.REVIEWED: "Đã đánh dấu góp ý là đã xem.",
            CommunityFeedback.Status.CLOSED: "Đã đánh dấu góp ý là đã xử lý.",
        }
        if status not in allowed_statuses:
            raise Http404

        feedback.status = status
        feedback.reviewed_at = feedback.reviewed_at or timezone.now()
        feedback.save(update_fields=("status", "reviewed_at"))
        self.message_user(
            request,
            allowed_statuses[status],
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(
            reverse("admin:rescue_communityfeedback_changelist")
        )

    def open_chat_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(("POST",))
        feedback = self.get_object(request, object_id)
        if feedback is None:
            raise Http404
        if not self.has_change_permission(request, feedback):
            raise PermissionDenied
        if feedback.user_id is None:
            self.message_user(
                request,
                "Người gửi dùng tài khoản khách. Hãy trả lời qua Gmail.",
                level=messages.WARNING,
            )
            return HttpResponseRedirect(
                reverse(
                    "admin:rescue_communityfeedback_change",
                    args=(feedback.pk,),
                )
            )

        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=feedback.user_id)
            conversation = (
                SupportConversation.objects.select_for_update()
                .filter(user_id=feedback.user_id)
                .exclude(status=SupportConversation.Status.CLOSED)
                .first()
            )
            if conversation is None:
                conversation = SupportConversation.objects.create(
                    user_id=feedback.user_id,
                    assigned_to=request.user,
                    subject=f"Phản hồi góp ý #{feedback.pk}"[:180],
                )
            elif conversation.assigned_to_id is None:
                conversation.assigned_to = request.user
                conversation.save(update_fields=("assigned_to", "updated_at"))

            if feedback.status == CommunityFeedback.Status.NEW:
                feedback.status = CommunityFeedback.Status.REVIEWED
                feedback.reviewed_at = timezone.now()
                feedback.save(update_fields=("status", "reviewed_at"))

        self.message_user(
            request,
            "Đã mở cuộc trò chuyện với người gửi góp ý.",
            level=messages.SUCCESS,
        )
        return HttpResponseRedirect(
            reverse("support:inbox")
            + f"?conversation={conversation.pk}&feedback={feedback.pk}"
        )

    def save_model(self, request, obj, form, change):
        if obj.status == CommunityFeedback.Status.NEW:
            obj.reviewed_at = None
        else:
            obj.reviewed_at = obj.reviewed_at or timezone.now()
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False
