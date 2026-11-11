from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.db.models import Case, CharField, F, Q, TextField, Value, When
from django.urls import reverse

from .models import Notification, RescueAssignment
from .permissions import is_rescue_admin


def _notification_display(queryset, user, assigned_cases=None):
    """Dựng nội dung được phép đọc, kể cả thông báo cũ đã lưu ghi chú riêng."""
    if is_rescue_admin(user):
        return queryset.annotate(display_title=F("title"), display_message=F("message"))
    if assigned_cases is None:
        assigned_cases = RescueAssignment.objects.filter(
            assignee=user, is_active=True,
        ).values("rescue_case_id")
    private_review = ~Q(rescue_case_id__in=assigned_cases)
    return queryset.annotate(
        display_title=Case(
            When(private_review & Q(kind=Notification.Kind.STATUS_CHANGED),
                 then=Value("Trạng thái ca cứu hộ đã thay đổi")),
            When(private_review & Q(kind=Notification.Kind.CASE_UPDATED),
                 then=Value("Có cập nhật mới từ đội cứu hộ")),
            default=F("title"), output_field=CharField(),
        ),
        display_message=Case(
            When(private_review & Q(kind=Notification.Kind.STATUS_CHANGED),
                 then=Value("Trạng thái xử lý đã được cập nhật. Mở hồ sơ để xem các mốc xử lý.")),
            When(private_review & Q(kind=Notification.Kind.CASE_UPDATED),
                 then=Value("Đội cứu hộ đã cập nhật tiến độ. Ghi chú hiện trường chỉ dành cho người có quyền xử lý.")),
            default=F("message"), output_field=TextField(),
        ),
    )


def available_notifications(user):
    if not user or not user.is_authenticated or not user.is_active:
        return Notification.objects.none()
    notifications = Notification.objects.filter(recipient=user).exclude(kind__startswith="adoption_")
    if is_rescue_admin(user):
        return _notification_display(notifications, user)

    # Thu hồi phân công cũng thu hồi thông báo chứa chỉ dẫn và liên hệ của ca đó.
    assigned_cases = RescueAssignment.objects.filter(
        assignee=user, is_active=True,
    ).values("rescue_case_id")
    notifications = notifications.exclude(kind=Notification.Kind.CASE_REPORTED).filter(
        Q(rescue_case__isnull=True) | Q(rescue_case__reporter=user)
        | Q(rescue_case_id__in=assigned_cases)
    ).exclude(
        Q(kind=Notification.Kind.CASE_MESSAGE)
        & ~Q(rescue_case_id__in=assigned_cases)
    )

    # Thông báo chat cũ không được giữ quyền đọc khi hội thoại đã giao sang người khác.
    from support.models import SupportConversation

    allowed_conversations = set(SupportConversation.objects.filter(
        assigned_to=user,
    ).values_list("pk", flat=True))
    inbox_path = reverse("support:inbox")
    blocked_ids = []
    for notification_id, target in notifications.filter(
        kind=Notification.Kind.SUPPORT_MESSAGE,
    ).values_list("pk", "target_url"):
        try:
            parts = urlsplit(target)
        except ValueError:
            # Liên kết hỏng được bộ dựng URL đưa về trang thông báo an toàn.
            continue
        if parts.path != inbox_path:
            continue
        values = parse_qs(parts.query).get("conversation", [])
        if (
            len(values) != 1 or not values[0].isascii() or not values[0].isdigit()
            or len(values[0]) > 19 or int(values[0]) not in allowed_conversations
        ):
            blocked_ids.append(notification_id)
    return _notification_display(notifications.exclude(pk__in=blocked_ids), user, assigned_cases)


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
    """Tạo một thông báo cho mỗi người nhận, loại trừ người đang thực hiện thao tác."""
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
    recipient_ids.update(
        get_user_model().objects.filter(is_active=True, is_superuser=True)
        .values_list("pk", flat=True)
    )
    return recipient_ids
