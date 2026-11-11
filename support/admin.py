from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from accounts.permissions import is_support_operator, support_operator_queryset

from .models import SupportAttachment, SupportConversation, SupportMessage


class SupportConversationAdminForm(forms.ModelForm):
    class Meta:
        model = SupportConversation
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "assigned_to" in self.fields:
            self.fields["assigned_to"].queryset = support_operator_queryset(
                SupportConversation._meta.get_field("assigned_to").remote_field.model
            )


class SupportMessageAdminForm(forms.ModelForm):
    class Meta:
        model = SupportMessage
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        body = cleaned_data.get("body", "").strip()
        if not body and not (
            self.instance.pk and self.instance.attachments.exists()
        ):
            self.add_error("body", "Tin nhắn phải có nội dung hoặc tệp đính kèm.")
        cleaned_data["body"] = body
        return cleaned_data


class SupportVisibilityAdminMixin:
    conversation_lookup = ""

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        if not is_support_operator(request.user):
            return queryset.none()
        prefix = self.conversation_lookup
        return queryset.filter(**{prefix + "assigned_to_id": request.user.pk})


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    readonly_fields = (
        "sender",
        "sender_role",
        "body",
        "is_read_by_admin",
        "is_read_by_user",
        "created_at",
    )
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupportConversation)
class SupportConversationAdmin(SupportVisibilityAdminMixin, admin.ModelAdmin):
    form = SupportConversationAdminForm
    list_display = (
        "user",
        "status",
        "assigned_to",
        "last_message_at",
        "created_at",
        "inbox_link",
    )
    list_filter = ("status", "last_message_at")
    search_fields = ("user__email", "user__full_name", "subject")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at", "last_message_at", "inbox_link")
    list_select_related = ("user", "assigned_to")
    inlines = (SupportMessageInline,)

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:
            fields += ("assigned_to",)
        if obj:
            fields += ("user", "status")
        return fields

    def has_add_permission(self, request):
        # Nhân sự hỗ trợ không được tự tạo/phân hội thoại để đọc thông tin người dùng khác.
        return request.user.is_superuser and super().has_add_permission(request)

    @admin.display(description="Trao đổi và xử lý")
    def inbox_link(self, obj):
        if not obj or not obj.pk:
            return "Lưu cuộc trò chuyện để mở hộp thư hỗ trợ."
        return format_html(
            '<a href="{}?conversation={}">Mở hộp thư · Trả lời / đóng / mở lại</a>',
            reverse("support:inbox"),
            obj.pk,
        )


@admin.register(SupportMessage)
class SupportMessageAdmin(SupportVisibilityAdminMixin, admin.ModelAdmin):
    form = SupportMessageAdminForm
    conversation_lookup = "conversation__"
    list_display = ("conversation", "sender", "sender_role", "created_at", "inbox_link")
    list_filter = ("sender_role", "is_read_by_admin", "is_read_by_user")
    search_fields = ("body", "sender__email", "conversation__user__email")
    readonly_fields = (
        "conversation", "sender", "sender_role", "is_read_by_admin",
        "is_read_by_user", "created_at", "inbox_link",
    )
    list_select_related = ("conversation", "sender")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Gửi tin nhắn")
    def inbox_link(self, obj):
        return format_html(
            '<a href="{}?conversation={}">Mở hộp thư để gửi tin nhắn</a>',
            reverse("support:inbox"),
            obj.conversation_id,
        )


@admin.register(SupportAttachment)
class SupportAttachmentAdmin(SupportVisibilityAdminMixin, admin.ModelAdmin):
    conversation_lookup = "message__conversation__"
    list_display = (
        "original_name",
        "media_type",
        "message",
        "size",
        "uploaded_at",
    )
    list_filter = ("media_type", "uploaded_at")
    search_fields = (
        "original_name",
        "message__body",
        "message__conversation__user__email",
    )
    readonly_fields = (
        "secure_download",
        "message",
        "media_type",
        "original_name",
        "size",
        "content_type",
        "uploaded_at",
    )
    fields = readonly_fields
    list_select_related = ("message", "message__conversation")

    @admin.display(description="Tệp đính kèm")
    def secure_download(self, obj):
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}</a>',
            reverse("support:attachment", args=(obj.pk,)),
            obj.original_name,
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        match = getattr(request, "resolver_match", None)
        deleting_parent = bool(match and match.url_name in {
            "support_supportconversation_delete", "support_supportconversation_changelist",
            "support_supportmessage_delete", "support_supportmessage_changelist",
        })
        if not deleting_parent and obj and not obj.message.body.strip() and obj.message.attachments.count() == 1:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
