from .models import Notification


def create_notifications(
    *,
    recipient_ids,
    kind,
    title,
    message,
    actor=None,
    rescue_case=None,
    target_url="",
):
    unique_recipient_ids = {recipient_id for recipient_id in recipient_ids if recipient_id}
    if actor is not None:
        unique_recipient_ids.discard(actor.pk)

    notifications = [
        Notification(
            recipient_id=recipient_id,
            actor=actor,
            rescue_case=rescue_case,
            target_url=target_url,
            kind=kind,
            title=title,
            message=message,
        )
        for recipient_id in unique_recipient_ids
    ]
    return Notification.objects.bulk_create(notifications)


def create_case_notifications(
    *,
    recipient_ids,
    rescue_case,
    kind,
    title,
    message,
    actor=None,
):
    """Create one notification per recipient, excluding the person acting."""
    return create_notifications(
        recipient_ids=recipient_ids,
        rescue_case=rescue_case,
        kind=kind,
        title=title,
        message=message,
        actor=actor,
    )


def case_participant_ids(rescue_case):
    recipient_ids = set(
        rescue_case.assignments.filter(is_active=True).values_list(
            "assignee_id",
            flat=True,
        )
    )
    if rescue_case.reporter_id:
        recipient_ids.add(rescue_case.reporter_id)
    return recipient_ids
