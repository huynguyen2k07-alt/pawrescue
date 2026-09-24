from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from organizations.models import OrganizationMembership, RescueOrganization
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


PAWRESCUE_ORGANIZATION_NAME = "PawRescue"


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


def _pawrescue_organization(user):
    organization, created = RescueOrganization.objects.get_or_create(
        name=PAWRESCUE_ORGANIZATION_NAME,
        defaults={
            "description": "Đội điều phối mặc định của trung tâm PawRescue.",
            "is_verified": True,
            "is_active": True,
            "created_by": user,
        },
    )
    organization_updates = []
    if not organization.is_verified:
        organization.is_verified = True
        organization_updates.append("is_verified")
    if not organization.is_active:
        organization.is_active = True
        organization_updates.append("is_active")
    if organization_updates:
        organization.save(update_fields=organization_updates + ["updated_at"])

    membership, _created = OrganizationMembership.objects.get_or_create(
        organization=organization,
        user=user,
        defaults={"role": OrganizationMembership.Role.MANAGER},
    )
    membership_updates = []
    if membership.role == OrganizationMembership.Role.VOLUNTEER:
        membership.role = OrganizationMembership.Role.MANAGER
        membership_updates.append("role")
    if not membership.is_active:
        membership.is_active = True
        membership_updates.append("is_active")
    if membership_updates:
        membership.save(update_fields=membership_updates)
    return organization


def _accept_case(case, organization, actor):
    if case.organization_id is not None:
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


class RescueCaseImageInline(admin.TabularInline):
    model = RescueCaseImage
    extra = 0
    autocomplete_fields = ("uploaded_by",)
    readonly_fields = ("uploaded_at",)


class RescueAssignmentInline(admin.TabularInline):
    model = RescueAssignment
    extra = 0
    fk_name = "rescue_case"
    autocomplete_fields = ("assignee", "assigned_by")
    readonly_fields = ("assigned_at",)


class CaseStatusHistoryInline(admin.TabularInline):
    model = CaseStatusHistory
    extra = 0
    fields = ("from_status", "to_status", "changed_by", "note", "changed_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class RescueUpdateInline(admin.TabularInline):
    model = RescueUpdate
    extra = 0
    autocomplete_fields = ("author",)
    readonly_fields = ("created_at",)


@admin.register(RescueCase)
class RescueCaseAdmin(admin.ModelAdmin):
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
    inlines = (
        RescueCaseImageInline,
        RescueAssignmentInline,
        CaseStatusHistoryInline,
        RescueUpdateInline,
    )

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
        }
        if status not in allowed_statuses:
            raise Http404

        success_message, history_note = allowed_statuses[status]
        with transaction.atomic():
            rescue_case = RescueCase.objects.select_for_update().get(
                pk=rescue_case.pk
            )
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
        terminal_statuses = {
            RescueCase.Status.RESCUED,
            RescueCase.Status.CLOSED,
            RescueCase.Status.CANCELLED,
        }
        extra_context = {
            **(extra_context or {}),
            "accept_case_available": bool(
                rescue_case
                and rescue_case.organization_id is None
                and rescue_case.status not in terminal_statuses
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
                f"Bỏ qua {skipped_count} ca đã có đơn vị tiếp nhận.",
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
        )
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
            self.message_user(
                request,
                "Đã tiếp nhận ca bởi PawRescue. Người báo tin cũng đã được thông báo.",
                level=messages.SUCCESS,
            )
            return HttpResponseRedirect(".")
        return super().response_change(request, obj)


@admin.register(RescueCaseImage)
class RescueCaseImageAdmin(admin.ModelAdmin):
    list_display = ("rescue_case", "caption", "uploaded_by", "uploaded_at")
    search_fields = ("rescue_case__title", "caption")
    autocomplete_fields = ("rescue_case", "uploaded_by")
    readonly_fields = ("uploaded_at",)


@admin.register(RescueAssignment)
class RescueAssignmentAdmin(admin.ModelAdmin):
    list_display = ("rescue_case", "assignee", "is_active", "assigned_at")
    list_filter = ("is_active",)
    search_fields = (
        "rescue_case__title",
        "assignee__email",
        "assignee__full_name",
    )
    autocomplete_fields = ("rescue_case", "assignee", "assigned_by")
    readonly_fields = ("assigned_at",)


@admin.register(CaseStatusHistory)
class CaseStatusHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "rescue_case",
        "from_status",
        "to_status",
        "changed_by",
        "changed_at",
    )
    list_filter = ("to_status",)
    search_fields = ("rescue_case__title", "changed_by__email", "note")
    autocomplete_fields = ("rescue_case", "changed_by")
    readonly_fields = ("changed_at",)


class RescueUpdateImageInline(admin.TabularInline):
    model = RescueUpdateImage
    extra = 0
    readonly_fields = ("uploaded_at",)


@admin.register(RescueUpdate)
class RescueUpdateAdmin(admin.ModelAdmin):
    list_display = ("rescue_case", "author", "created_at")
    search_fields = ("rescue_case__title", "author__email", "note")
    autocomplete_fields = ("rescue_case", "author")
    readonly_fields = ("created_at",)
    inlines = (RescueUpdateImageInline,)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
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


@admin.register(ContributorProfile)
class ContributorProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "display_order", "is_active")
    list_editable = ("display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "role", "bio")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CommunityFeedback)
class CommunityFeedbackAdmin(admin.ModelAdmin):
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
        feedback_queryset = self.get_queryset(request).select_related("user")
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
        extra_context = {
            **(extra_context or {}),
            "feedback_counts": counts,
            "feedback_items": feedback_items,
        }
        return super().changelist_view(request, extra_context=extra_context)

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
