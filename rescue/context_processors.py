from .notifications import available_notifications
from accounts.permissions import is_support_operator


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}

    return {
        "rescue_has_workspace": is_support_operator(request.user) or request.user.rescue_assignments.filter(is_active=True).exists(),
        "unread_notification_count": available_notifications(request.user).filter(is_read=False).count()
    }
