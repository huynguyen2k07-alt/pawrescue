from django.contrib import admin

from .models import SupportAttachment, SupportConversation, SupportMessage


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

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupportConversation)
class SupportConversationAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "status",
        "assigned_to",
        "last_message_at",
        "created_at",
    )
    list_filter = ("status", "last_message_at")
    search_fields = ("user__email", "user__full_name", "subject")
    autocomplete_fields = ("user", "assigned_to")
    readonly_fields = ("created_at", "updated_at", "last_message_at")
    list_select_related = ("user", "assigned_to")
    inlines = (SupportMessageInline,)


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sender", "sender_role", "created_at")
    list_filter = ("sender_role", "is_read_by_admin", "is_read_by_user")
    search_fields = ("body", "sender__email", "conversation__user__email")
    autocomplete_fields = ("conversation", "sender")
    readonly_fields = ("created_at",)
    list_select_related = ("conversation", "sender")


@admin.register(SupportAttachment)
class SupportAttachmentAdmin(admin.ModelAdmin):
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
        "file",
        "message",
        "media_type",
        "original_name",
        "size",
        "content_type",
        "uploaded_at",
    )
    list_select_related = ("message", "message__conversation")

    def has_add_permission(self, request):
        return False
