from django.db.models import Q

from accounts.permissions import is_support_operator
from .models import SupportMessage


def support_chat(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "support_chat_unread_count": 0,
            "support_admin_unread_count": 0,
            "support_is_operator": False,
        }

    if is_support_operator(user):
        unread_messages = SupportMessage.objects.filter(
            sender_role=SupportMessage.SenderRole.USER,
            is_read_by_admin=False,
        )
        if not user.is_superuser:
            unread_messages = unread_messages.filter(
                Q(conversation__assigned_to__isnull=True)
                | Q(conversation__assigned_to=user)
            )
        return {
            "support_chat_unread_count": 0,
            "support_admin_unread_count": unread_messages.count(),
            "support_is_operator": True,
        }

    return {
        "support_chat_unread_count": SupportMessage.objects.filter(
            conversation__user=user,
            sender_role=SupportMessage.SenderRole.ADMIN,
            is_read_by_user=False,
        ).count(),
        "support_admin_unread_count": 0,
        "support_is_operator": False,
    }
