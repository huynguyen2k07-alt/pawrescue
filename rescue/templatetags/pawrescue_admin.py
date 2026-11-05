from django import template
from django.contrib import admin
from django.db.models import Count, Q

from accounts.permissions import is_support_operator
from rescue.models import RescueCase
from rescue.permissions import is_rescue_admin
from support.models import SupportConversation


register = template.Library()

ADMIN_LABELS = {
    "accounts.user": "Tài khoản và nhân sự",
    "organizations.rescueorganization": "Đơn vị tiếp nhận",
    "rescue.rescuecase": "Yêu cầu cứu hộ",
}


@register.simple_tag(takes_context=True)
def pawrescue_admin_dashboard(context, app_list=None):
    user = context.get("user")
    if not user or not user.is_authenticated or not user.is_staff:
        return {}

    request = context.get("request")
    for app in app_list or ():
        app_record_count = 0
        for model_info in app.get("models", ()):
            model = model_info["model"]
            model_key = model._meta.label_lower
            model_info["name"] = ADMIN_LABELS.get(model_key, model_info["name"])
            model_admin = admin.site._registry.get(model)
            queryset = (
                model_admin.get_queryset(request)
                if model_admin is not None and request is not None
                else model._default_manager.none()
            )
            record_count = queryset.count()
            model_info["record_count"] = record_count
            app_record_count += record_count
        app["record_count"] = app_record_count

    can_manage_cases = is_rescue_admin(user)
    cases = RescueCase.objects.all() if can_manage_cases else RescueCase.objects.none()
    terminal_statuses = (
        RescueCase.Status.RESCUED,
        RescueCase.Status.CLOSED,
        RescueCase.Status.CANCELLED,
    )
    active_cases = cases.exclude(status__in=terminal_statuses)
    counts = cases.aggregate(
        case_count=Count("pk"),
        reported_case_count=Count("pk", filter=Q(status=RescueCase.Status.REPORTED)),
        in_progress_case_count=Count("pk", filter=Q(status__in=(
            RescueCase.Status.VERIFIED,
            RescueCase.Status.ASSIGNED,
            RescueCase.Status.IN_PROGRESS,
            RescueCase.Status.PENDING_REVIEW,
        ))),
        completed_case_count=Count("pk", filter=Q(status__in=terminal_statuses)),
    )
    can_support = is_support_operator(user)
    pending_support = SupportConversation.objects.none()
    if can_support:
        pending_support = SupportConversation.objects.filter(
            status=SupportConversation.Status.WAITING_ADMIN
        )
        if not user.is_superuser:
            pending_support = pending_support.filter(Q(assigned_to__isnull=True) | Q(assigned_to=user))

    return {
        **counts,
        "can_manage_cases": can_manage_cases,
        "can_support": can_support,
        "active_case_count": active_cases.count(),
        "pending_support_count": pending_support.count(),
        "recent_cases": active_cases.order_by("-reported_at")[:8],
        "pending_conversations": pending_support.select_related("user").order_by("-last_message_at")[:5],
    }
