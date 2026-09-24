from .models import SupportConversation, SupportMessage


def support_chat(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "support_chat_unread_count": 0,
            "support_admin_unread_count": 0,
        }

    if user.is_staff:
        return {
            "support_chat_unread_count": 0,
            "support_admin_unread_count": SupportMessage.objects.filter(
                sender_role=SupportMessage.SenderRole.USER,
                is_read_by_admin=False,
            ).count(),
        }

    return {
        "support_chat_unread_count": SupportMessage.objects.filter(
            conversation__user=user,
            sender_role=SupportMessage.SenderRole.ADMIN,
            is_read_by_user=False,
        ).count(),
        "support_admin_unread_count": 0,
    }
