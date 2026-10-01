import calendar
from datetime import date

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from rescue.models import Notification
from rescue.notifications import create_notifications

from .models import AdoptionCheckInRequest, AdoptionPlacement


FOLLOW_UP_MONTHS = (1, 2, 3)


def add_months(value, months):
    """Return the same day N months later, clamped to that month's last day."""
    target_index = value.month - 1 + months
    year = value.year + target_index // 12
    month = target_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def ensure_follow_up_schedule(placement):
    """Create the fixed 1/2/3-month check-in schedule for a placement."""
    placed_on = timezone.localtime(placement.placed_at).date()
    for milestone in FOLLOW_UP_MONTHS:
        due_on = add_months(placed_on, milestone)
        check_in, created = AdoptionCheckInRequest.objects.get_or_create(
            placement=placement,
            milestone_month=milestone,
            defaults={"due_on": due_on},
        )
        if not created and not check_in.submitted_at and check_in.due_on != due_on:
            check_in.due_on = due_on
            check_in.save(update_fields=("due_on", "updated_at"))

    next_due = (
        placement.check_in_requests.filter(submitted_at__isnull=True)
        .order_by("due_on")
        .values_list("due_on", flat=True)
        .first()
    )
    AdoptionPlacement.objects.filter(pk=placement.pk).update(
        next_follow_up_on=next_due
    )
    return next_due


def dispatch_due_follow_up_reminders(today=None):
    """Send each due in-app reminder once, safe for repeated scheduler runs."""
    today = today or timezone.localdate()
    sent_count = 0
    due_ids = list(
        AdoptionCheckInRequest.objects.filter(
            due_on__lte=today,
            notification_sent_at__isnull=True,
            submitted_at__isnull=True,
            placement__is_active=True,
            placement__adopter__is_active=True,
        ).values_list("pk", flat=True)
    )
    for check_in_id in due_ids:
        with transaction.atomic():
            check_in = (
                AdoptionCheckInRequest.objects.select_for_update()
                .select_related("placement__animal", "placement__adopter")
                .filter(
                    pk=check_in_id,
                    notification_sent_at__isnull=True,
                    submitted_at__isnull=True,
                )
                .first()
            )
            if check_in is None:
                continue
            create_notifications(
                recipient_ids=(check_in.placement.adopter_id,),
                kind=Notification.Kind.ADOPTION_FOLLOW_UP,
                title=f"Đến lịch cập nhật tình hình {check_in.placement.animal.name}",
                message=(
                    f"Đã {check_in.milestone_month} tháng từ ngày nhận nuôi. "
                    "Hãy dành ít phút cho PawRescue biết pet đang thế nào."
                ),
                target_url=reverse(
                    "adoptions:check-in",
                    args=(check_in.pk,),
                ),
            )
            check_in.notification_sent_at = timezone.now()
            check_in.save(update_fields=("notification_sent_at", "updated_at"))
            sent_count += 1
    return sent_count
