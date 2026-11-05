from django.db.models import Count, Max, Q

from accounts.permissions import is_support_operator

from .notifications import available_notifications
from .permissions import is_rescue_moderator


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}

    counts = available_notifications(request.user).aggregate(
        unread=Count("pk", filter=Q(is_read=False)),
        latest=Max("pk"),
    )
    return {
        "rescue_has_workspace": is_support_operator(request.user) or is_rescue_moderator(request.user) or request.user.rescue_assignments.filter(is_active=True).exists(),
        "unread_notification_count": counts["unread"],
        "latest_notification_id": counts["latest"] or 0,
    }
