from django import template

from adoptions.models import AdoptionApplication, AdoptionSafetyReport
from donations.models import Donation
from rescue.models import Notification, RescueCase
from support.models import SupportConversation


register = template.Library()


@register.simple_tag(takes_context=True)
def pawrescue_admin_dashboard(context, app_list=None):
    user = context.get("user")
    if not user or not user.is_authenticated or not user.is_staff:
        return {}

    for app in app_list or ():
        app_record_count = 0
        for model_info in app.get("models", ()):
            record_count = model_info["model"]._default_manager.count()
            model_info["record_count"] = record_count
            app_record_count += record_count
        app["record_count"] = app_record_count

    active_cases = RescueCase.objects.exclude(
        status__in=(
            RescueCase.Status.CLOSED,
            RescueCase.Status.CANCELLED,
        )
    )
    pending_applications = AdoptionApplication.objects.filter(
        status__in=(
            AdoptionApplication.Status.PENDING,
            AdoptionApplication.Status.REVIEWING,
        )
    )
    pending_safety_reports = AdoptionSafetyReport.objects.filter(
        status__in=(
            AdoptionSafetyReport.Status.PENDING,
            AdoptionSafetyReport.Status.REVIEWING,
        )
    )
    pending_donations = Donation.objects.filter(status=Donation.Status.PENDING)
    unread_notifications = Notification.objects.filter(
        recipient=user,
        is_read=False,
    )
    pending_support = SupportConversation.objects.filter(
        status=SupportConversation.Status.WAITING_ADMIN
    )

    return {
        "active_case_count": active_cases.count(),
        "critical_case_count": active_cases.filter(
            urgency=RescueCase.Urgency.CRITICAL
        ).count(),
        "pending_application_count": pending_applications.count(),
        "pending_safety_count": pending_safety_reports.count(),
        "pending_donation_count": pending_donations.count(),
        "unread_notification_count": unread_notifications.count(),
        "pending_support_count": pending_support.count(),
        "recent_applications": pending_applications.select_related(
            "animal",
            "applicant",
            "animal__organization",
        ).order_by("-submitted_at")[:5],
        "recent_safety_reports": pending_safety_reports.select_related(
            "animal",
            "reporter",
        ).order_by("-submitted_at")[:4],
        "recent_notifications": unread_notifications.order_by("-created_at")[:5],
    }
