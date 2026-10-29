from pathlib import Path

from django.contrib import messages as django_messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST

from accounts.permissions import (
    is_support_operator,
    support_operator_queryset,
    support_operator_ids,
    support_operator_required,
)
from rescue.models import CommunityFeedback, Notification, RescueCase
from rescue.notifications import create_notifications
from rescue.permissions import is_case_assignee, is_rescue_admin

from .forms import SupportMessageForm
from .models import (
    IMAGE_EXTENSIONS,
    SupportAttachment,
    SupportConversation,
    SupportMessage,
)


def _operator_ids(conversation):
    # Khi đã phân người phụ trách, thông báo hỗ trợ chỉ gửi cho người đó và quản trị viên cao nhất.
    if conversation.assigned_to_id is None:
        return support_operator_ids(get_user_model())
    return support_operator_queryset(get_user_model()).filter(
        Q(is_superuser=True) | Q(pk=conversation.assigned_to_id)
    ).values_list("pk", flat=True)


def _serialize_message(message):
    local_created_at = timezone.localtime(message.created_at)
    return {
        "id": message.pk,
        "body": message.body,
        "is_admin": message.sender_role == SupportMessage.SenderRole.ADMIN,
        "sender_name": (
            "Đội hỗ trợ PawRescue"
            if message.sender_role == SupportMessage.SenderRole.ADMIN
            else message.sender.full_name or message.sender.email
        ),
        "created_at": local_created_at.strftime("%H:%M, %d/%m/%Y"),
        "attachments": [
            {
                "id": attachment.pk,
                "media_type": attachment.media_type,
                "url": reverse("support:attachment", args=(attachment.pk,)),
                "name": attachment.original_name,
                "content_type": attachment.content_type,
                "size": attachment.size,
            }
            for attachment in message.attachments.all()
        ],
    }


def _create_attachments(chat_message, uploaded_files):
    for uploaded_file in uploaded_files:
        extension = Path(uploaded_file.name).suffix.lower().lstrip(".")
        media_type = (
            SupportAttachment.MediaType.IMAGE
            if extension in IMAGE_EXTENSIONS
            else SupportAttachment.MediaType.VIDEO
        )
        SupportAttachment.objects.create(
            message=chat_message,
            file=uploaded_file,
            media_type=media_type,
            original_name=Path(uploaded_file.name).name[:255],
            content_type=uploaded_file.content_type[:100],
            size=uploaded_file.size,
        )


def _notification_preview(chat_message, attachment_count):
    if chat_message.body:
        return chat_message.body[:100]
    return f"Đã gửi {attachment_count} ảnh/video đính kèm."


def _operator_can_access_conversation(user, conversation):
    return user.is_superuser or conversation.assigned_to_id in {
        None,
        user.pk,
    }


def _operator_conversation_queryset(user):
    queryset = SupportConversation.objects.select_related("user", "assigned_to")
    if user.is_superuser:
        return queryset
    return queryset.filter(Q(assigned_to__isnull=True) | Q(assigned_to=user))


def _case_for_conversation(user, conversation, case_id):
    if not str(case_id).isdigit():
        return None
    rescue_case = RescueCase.objects.filter(pk=int(case_id), reporter_id=conversation.user_id).first()
    if rescue_case and (is_rescue_admin(user) or is_case_assignee(user, rescue_case)):
        return rescue_case
    return None


def _lock_operator_conversation(user, pk):
    """Khóa bản ghi hội thoại gốc rồi kiểm tra lại quyền của người phụ trách.

    Danh sách hội thoại có phép đếm tin chưa đọc. Khi cập nhật, khóa bảng gốc
    để tránh ghép truy vấn có nhóm dữ liệu với SELECT ... FOR UPDATE trên PostgreSQL.
    """

    # Khóa hội thoại rồi kiểm tra lại người phụ trách để tránh thao tác trên phân công đã đổi.
    conversation = (
        SupportConversation.objects.select_for_update()
        .filter(pk=pk)
        .first()
    )
    if conversation is None or not _operator_can_access_conversation(
        user,
        conversation,
    ):
        raise Http404
    return conversation


def _conversation_queryset(user):
    return (
        _operator_conversation_queryset(user)
        .annotate(
            unread_count=Count(
                "messages",
                filter=Q(
                    messages__sender_role=SupportMessage.SenderRole.USER,
                    messages__is_read_by_admin=False,
                ),
            )
        )
        .order_by("-last_message_at")
    )


@require_GET
@login_required
def attachment(request, pk):
    item = get_object_or_404(
        SupportAttachment.objects.select_related("message__conversation"),
        pk=pk,
    )
    conversation = item.message.conversation
    is_owner = conversation.user_id == request.user.pk
    can_operate = is_support_operator(request.user) and (
        request.user.is_superuser
        or conversation.assigned_to_id in {None, request.user.pk}
    )
    if not is_owner and not can_operate:
        raise Http404

    try:
        file_handle = item.file.open("rb")
    except FileNotFoundError as error:
        raise Http404 from error

    response = FileResponse(file_handle, content_type=item.content_type)
    response.headers["Content-Disposition"] = content_disposition_header(
        False,
        item.original_name,
    )
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _serialize_conversation(conversation):
    display_name = conversation.user.full_name or conversation.user.email
    return {
        "id": conversation.pk,
        "name": display_name,
        "email": conversation.user.email,
        "avatar": display_name[:1].upper(),
        "status": conversation.status,
        "status_label": conversation.get_status_display(),
        "unread_count": conversation.unread_count,
        "last_message_at": timezone.localtime(
            conversation.last_message_at
        ).strftime("%H:%M, %d/%m/%Y"),
        "url": reverse("support:inbox") + f"?conversation={conversation.pk}",
    }


@require_GET
@login_required
def chat_state(request):
    if is_support_operator(request.user):
        return JsonResponse(
            {"error": "Đội hỗ trợ sử dụng Hộp thư cộng tác viên."},
            status=403,
        )

    conversation = (
        SupportConversation.objects.filter(user=request.user)
        .select_related("assigned_to")
        .first()
    )
    if not conversation:
        return JsonResponse(
            {
                "conversation_id": None,
                "status": "new",
                "status_label": "Sẵn sàng hỗ trợ",
                "unread_count": 0,
                "messages": [],
            }
        )

    mark_read = request.GET.get("mark_read") == "1"
    if mark_read:
        conversation.messages.filter(
            sender_role=SupportMessage.SenderRole.ADMIN,
            is_read_by_user=False,
        ).update(is_read_by_user=True)
        unread_count = 0
    else:
        unread_count = conversation.messages.filter(
            sender_role=SupportMessage.SenderRole.ADMIN,
            is_read_by_user=False,
        ).count()
    recent_messages = list(
        conversation.messages.select_related("sender")
        .prefetch_related("attachments")
        .order_by("-created_at", "-pk")[:50]
    )
    recent_messages.reverse()
    return JsonResponse(
        {
            "conversation_id": conversation.pk,
            "status": conversation.status,
            "status_label": conversation.get_status_display(),
            "unread_count": unread_count,
            "messages": [_serialize_message(item) for item in recent_messages],
        }
    )


@require_POST
@login_required
def chat_send(request):
    if is_support_operator(request.user):
        return JsonResponse(
            {"error": "Đội hỗ trợ vui lòng trả lời trong Hộp thư cộng tác viên."},
            status=403,
        )

    form = SupportMessageForm(request.POST, request.FILES)
    if not form.is_valid():
        error = next(iter(form.errors.values()))[0]
        return JsonResponse({"error": str(error)}, status=400)

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        conversation = (
            SupportConversation.objects.select_for_update()
            .filter(user=request.user)
            .exclude(status=SupportConversation.Status.CLOSED)
            .first()
        )
        if conversation is None:
            conversation = SupportConversation.objects.create(user=request.user)

        chat_message = SupportMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            sender_role=SupportMessage.SenderRole.USER,
            body=form.cleaned_data["body"],
            is_read_by_user=True,
        )
        _create_attachments(chat_message, form.cleaned_data["attachments"])
        attachment_count = len(form.cleaned_data["attachments"])
        conversation.status = SupportConversation.Status.WAITING_ADMIN
        conversation.last_message_at = chat_message.created_at
        conversation.save(update_fields=("status", "last_message_at", "updated_at"))

        create_notifications(
            recipient_ids=_operator_ids(conversation),
            kind=Notification.Kind.SUPPORT_MESSAGE,
            title="Có tin nhắn hỗ trợ mới",
            message=(
                f"{request.user.full_name or request.user.email}: "
                f"{_notification_preview(chat_message, attachment_count)}"
            ),
            actor=request.user,
            target_url=(
                reverse("support:inbox") + f"?conversation={conversation.pk}"
            ),
        )

    return JsonResponse(
        {
            "message": _serialize_message(chat_message),
            "status": conversation.status,
            "status_label": conversation.get_status_display(),
        },
        status=201,
    )


@support_operator_required
def inbox(request):
    conversations = _conversation_queryset(request.user)
    selected = None
    selected_id = request.GET.get("conversation")
    if selected_id and selected_id.isdigit():
        selected = conversations.filter(pk=int(selected_id)).first()
    if selected is None:
        selected = conversations.first()

    chat_messages = SupportMessage.objects.none()
    context_case = None
    context_feedback = None
    draft_message = ""
    if selected:
        selected.messages.filter(
            sender_role=SupportMessage.SenderRole.USER,
            is_read_by_admin=False,
        ).update(is_read_by_admin=True)
        chat_messages = selected.messages.select_related("sender").prefetch_related(
            "attachments"
        )
        context_case = _case_for_conversation(request.user, selected, request.GET.get("case", ""))
        if context_case and request.GET.get("sent") != "1":
            display_name = selected.user.full_name or "bạn"
            draft_message = (
                f"Chào {display_name}, PawRescue liên hệ với bạn về ca "
                f'#{context_case.pk} “{context_case.title}”. '
                "Bạn có thể trao đổi thêm tình hình với đội ngũ tại đây nhé."
            )
        feedback_id = request.GET.get("feedback", "")
        if feedback_id.isdigit():
            context_feedback = CommunityFeedback.objects.filter(
                pk=int(feedback_id),
                user_id=selected.user_id,
            ).first()
        if context_feedback:
            display_name = selected.user.full_name or "bạn"
            draft_message = (
                f"Chào {display_name}, PawRescue đã nhận được góp ý "
                f'#{context_feedback.pk} về “{context_feedback.get_category_display()}”. '
                "Cảm ơn bạn đã chia sẻ. PawRescue xin phản hồi như sau: "
            )

    template_name = (
        "support/inbox.html"
        if request.user.is_superuser
        else "support/collaborator_inbox.html"
    )
    return render(
        request,
        template_name,
        {
            "conversations": conversations,
            "selected_conversation": selected,
            "chat_messages": chat_messages,
            "reply_form": SupportMessageForm(),
            "context_case": context_case,
            "context_feedback": context_feedback,
            "draft_message": draft_message,
        },
    )


@require_POST
@support_operator_required
def open_case_chat(request, pk):
    rescue_case = get_object_or_404(
        RescueCase.objects.select_related("reporter"),
        pk=pk,
    )
    if not (is_rescue_admin(request.user) or is_case_assignee(request.user, rescue_case)):
        raise Http404
    return_url = (
        reverse("admin:rescue_rescuecase_change", args=(rescue_case.pk,))
        if request.user.is_superuser
        else reverse("collaborators:dashboard")
    )
    if rescue_case.reporter_id is None:
        django_messages.error(
            request,
            "Ca này không có tài khoản người báo tin để mở cuộc trò chuyện.",
        )
        return redirect(return_url)

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(
            pk=rescue_case.reporter_id
        )
        conversation = (
            SupportConversation.objects.select_for_update()
            .filter(user_id=rescue_case.reporter_id)
            .exclude(status=SupportConversation.Status.CLOSED)
            .first()
        )
        if conversation is None:
            conversation = SupportConversation.objects.create(
                user_id=rescue_case.reporter_id,
                assigned_to=request.user,
                subject=f"Trao đổi về ca #{rescue_case.pk}: {rescue_case.title}"[:180],
            )
        elif (
            conversation.assigned_to_id is not None
            and conversation.assigned_to_id != request.user.pk
            and not request.user.is_superuser
        ):
            django_messages.info(
                request,
                "Cuộc trò chuyện này đang được một cộng tác viên khác phụ trách.",
            )
            return redirect(return_url)
        elif conversation.assigned_to_id is None:
            conversation.assigned_to = request.user
            conversation.save(update_fields=("assigned_to", "updated_at"))

    django_messages.success(
        request,
        "Đã mở cuộc trò chuyện với người báo tin. Tin nhắn mẫu đã được điền sẵn.",
    )
    return redirect(
        reverse("support:inbox")
        + f"?conversation={conversation.pk}&case={rescue_case.pk}"
    )


@require_GET
@support_operator_required
def inbox_state(request):
    conversations = _conversation_queryset(request.user)
    selected = None
    selected_id = request.GET.get("conversation")
    if selected_id and selected_id.isdigit():
        selected = conversations.filter(pk=int(selected_id)).first()
    if selected is None:
        selected = conversations.first()

    selected_payload = None
    if selected:
        selected.messages.filter(
            sender_role=SupportMessage.SenderRole.USER,
            is_read_by_admin=False,
        ).update(is_read_by_admin=True)
        recent_messages = list(
            selected.messages.select_related("sender")
            .prefetch_related("attachments")
            .order_by("-created_at", "-pk")[:100]
        )
        recent_messages.reverse()
        selected_payload = {
            "id": selected.pk,
            "status": selected.status,
            "status_label": selected.get_status_display(),
            "messages": [_serialize_message(item) for item in recent_messages],
        }

    conversations = _conversation_queryset(request.user)
    return JsonResponse(
        {
            "conversations": [
                _serialize_conversation(item) for item in conversations
            ],
            "selected": selected_payload,
        }
    )


@require_POST
@support_operator_required
def admin_reply(request, pk):
    snapshot = get_object_or_404(
        _operator_conversation_queryset(request.user),
        pk=pk,
    )
    return_url = reverse("support:inbox") + f"?conversation={pk}"
    context_case = _case_for_conversation(request.user, snapshot, request.POST.get("case", ""))
    if context_case:
        return_url += f"&case={context_case.pk}"
    form = SupportMessageForm(request.POST, request.FILES)
    if not form.is_valid():
        error = next(iter(form.errors.values()))[0]
        django_messages.error(request, str(error))
        return redirect(return_url)

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=snapshot.user_id)
        conversation = _lock_operator_conversation(request.user, pk)
        if conversation.status == SupportConversation.Status.CLOSED:
            django_messages.error(request, "Cuộc trò chuyện này đã được đóng.")
            return redirect(return_url)
        chat_message = SupportMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            sender_role=SupportMessage.SenderRole.ADMIN,
            body=form.cleaned_data["body"],
            is_read_by_admin=True,
        )
        _create_attachments(chat_message, form.cleaned_data["attachments"])
        attachment_count = len(form.cleaned_data["attachments"])
        conversation.assigned_to = request.user
        conversation.status = SupportConversation.Status.WAITING_USER
        conversation.last_message_at = chat_message.created_at
        conversation.save(
            update_fields=(
                "assigned_to",
                "status",
                "last_message_at",
                "updated_at",
            )
        )
        create_notifications(
            recipient_ids=(conversation.user_id,),
            kind=Notification.Kind.SUPPORT_MESSAGE,
            title="Đội hỗ trợ đã trả lời",
            message=_notification_preview(chat_message, attachment_count),
            actor=request.user,
            target_url=reverse("rescue:case-list"),
        )

    django_messages.success(request, "Đã gửi câu trả lời tới người dùng.")
    return redirect(return_url + ("&sent=1" if context_case else ""))


@require_POST
@support_operator_required
def close_conversation(request, pk):
    snapshot = get_object_or_404(
        _operator_conversation_queryset(request.user),
        pk=pk,
    )
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=snapshot.user_id)
        conversation = _lock_operator_conversation(request.user, pk)
        if conversation.status == SupportConversation.Status.CLOSED:
            django_messages.info(request, "Cuộc trò chuyện này đã được đóng trước đó.")
            return redirect(reverse("support:inbox") + f"?conversation={pk}")

        conversation.status = SupportConversation.Status.CLOSED
        conversation.assigned_to = request.user
        conversation.save(update_fields=("status", "assigned_to", "updated_at"))
        create_notifications(
            recipient_ids=(conversation.user_id,),
            kind=Notification.Kind.SUPPORT_MESSAGE,
            title="Cuộc trò chuyện hỗ trợ đã kết thúc",
            message="Bạn vẫn có thể gửi tin nhắn mới nếu cần hỗ trợ thêm.",
            actor=request.user,
            target_url=reverse("rescue:case-list"),
        )
    django_messages.success(request, "Đã đóng cuộc trò chuyện.")
    return redirect(reverse("support:inbox") + f"?conversation={pk}")


@require_POST
@support_operator_required
def reopen_conversation(request, pk):
    snapshot = get_object_or_404(
        _operator_conversation_queryset(request.user),
        pk=pk,
    )
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=snapshot.user_id)
        conversation = _lock_operator_conversation(request.user, pk)

        if conversation.status != SupportConversation.Status.CLOSED:
            django_messages.info(request, "Cuộc trò chuyện này đang hoạt động.")
            return redirect(reverse("support:inbox") + f"?conversation={pk}")

        has_active_conversation = (
            SupportConversation.objects.select_for_update()
            .filter(user_id=conversation.user_id)
            .exclude(pk=conversation.pk)
            .exclude(status=SupportConversation.Status.CLOSED)
            .exists()
        )
        if has_active_conversation:
            django_messages.error(
                request,
                "Người dùng đã có một cuộc trò chuyện đang hoạt động; "
                "không thể mở lại luồng cũ.",
            )
            return redirect("support:inbox")

        conversation.status = SupportConversation.Status.WAITING_ADMIN
        if conversation.assigned_to_id is None:
            conversation.assigned_to = request.user
        conversation.save(update_fields=("status", "assigned_to", "updated_at"))

    django_messages.success(request, "Đã mở lại cuộc trò chuyện.")
    return redirect(reverse("support:inbox") + f"?conversation={pk}")
