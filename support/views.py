from pathlib import Path

from django.contrib import messages as django_messages
from django.contrib.admin.views.decorators import staff_member_required
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

from rescue.models import CommunityFeedback, Notification, RescueCase
from rescue.notifications import create_notifications

from .forms import SupportMessageForm
from .models import (
    IMAGE_EXTENSIONS,
    SupportAttachment,
    SupportConversation,
    SupportMessage,
)


def _staff_ids():
    return get_user_model().objects.filter(
        is_active=True,
        is_staff=True,
    ).values_list("pk", flat=True)


def _serialize_message(message):
    local_created_at = timezone.localtime(message.created_at)
    return {
        "id": message.pk,
        "body": message.body,
        "is_admin": message.sender_role == SupportMessage.SenderRole.ADMIN,
        "sender_name": (
            "Quản trị viên PawRescue"
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


def _notification_preview(chat_message):
    if chat_message.body:
        return chat_message.body[:100]
    attachment_count = chat_message.attachments.count()
    return f"Đã gửi {attachment_count} ảnh/video đính kèm."


def _conversation_queryset():
    return (
        SupportConversation.objects.select_related("user", "assigned_to")
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
    if not request.user.is_staff and item.message.conversation.user_id != request.user.pk:
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
    if request.user.is_staff:
        return JsonResponse(
            {"error": "Quản trị viên sử dụng Hộp thư hỗ trợ."},
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

    if request.GET.get("mark_read") == "1":
        conversation.messages.filter(
            sender_role=SupportMessage.SenderRole.ADMIN,
            is_read_by_user=False,
        ).update(is_read_by_user=True)
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
    if request.user.is_staff:
        return JsonResponse(
            {"error": "Quản trị viên vui lòng trả lời trong Hộp thư hỗ trợ."},
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
        conversation.status = SupportConversation.Status.WAITING_ADMIN
        conversation.last_message_at = chat_message.created_at
        conversation.save(update_fields=("status", "last_message_at", "updated_at"))

        create_notifications(
            recipient_ids=_staff_ids(),
            kind=Notification.Kind.SUPPORT_MESSAGE,
            title="Có tin nhắn hỗ trợ mới",
            message=(
                f"{request.user.full_name or request.user.email}: "
                f"{_notification_preview(chat_message)}"
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


@staff_member_required
def inbox(request):
    conversations = _conversation_queryset()
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
        case_id = request.GET.get("case", "")
        if case_id.isdigit():
            context_case = RescueCase.objects.filter(
                pk=int(case_id),
                reporter_id=selected.user_id,
            ).first()
        if context_case:
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

    return render(
        request,
        "support/inbox.html",
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
@staff_member_required
def open_case_chat(request, pk):
    rescue_case = get_object_or_404(
        RescueCase.objects.select_related("reporter"),
        pk=pk,
    )
    admin_change_url = reverse(
        "admin:rescue_rescuecase_change",
        args=(rescue_case.pk,),
    )
    if rescue_case.reporter_id is None:
        django_messages.error(
            request,
            "Ca này không có tài khoản người báo tin để mở cuộc trò chuyện.",
        )
        return redirect(admin_change_url)

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
@staff_member_required
def inbox_state(request):
    conversations = _conversation_queryset()
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

    # Re-query after marking the selected thread as read so its badge is current.
    conversations = _conversation_queryset()
    return JsonResponse(
        {
            "conversations": [
                _serialize_conversation(item) for item in conversations
            ],
            "selected": selected_payload,
        }
    )


@require_POST
@staff_member_required
def admin_reply(request, pk):
    form = SupportMessageForm(request.POST, request.FILES)
    conversation = get_object_or_404(
        SupportConversation.objects.select_related("user"),
        pk=pk,
    )
    if conversation.status == SupportConversation.Status.CLOSED:
        django_messages.error(request, "Cuộc trò chuyện này đã được đóng.")
        return redirect(reverse("support:inbox") + f"?conversation={pk}")
    if not form.is_valid():
        error = next(iter(form.errors.values()))[0]
        django_messages.error(request, str(error))
        return redirect(reverse("support:inbox") + f"?conversation={pk}")

    with transaction.atomic():
        conversation = SupportConversation.objects.select_for_update().get(pk=pk)
        chat_message = SupportMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            sender_role=SupportMessage.SenderRole.ADMIN,
            body=form.cleaned_data["body"],
            is_read_by_admin=True,
        )
        _create_attachments(chat_message, form.cleaned_data["attachments"])
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
            title="Quản trị viên đã trả lời",
            message=_notification_preview(chat_message),
            actor=request.user,
            target_url=reverse("rescue:case-list"),
        )

    django_messages.success(request, "Đã gửi câu trả lời tới người dùng.")
    return redirect(reverse("support:inbox") + f"?conversation={pk}")


@require_POST
@staff_member_required
def close_conversation(request, pk):
    conversation = get_object_or_404(
        SupportConversation.objects.select_related("user"),
        pk=pk,
    )
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
    return redirect("support:inbox")
