from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render

from rescue.models import Notification, RescueCase
from support.models import SupportConversation, SupportMessage

from .forms import RegistrationForm
from .permissions import support_operator_required


def register(request):
    if request.user.is_authenticated:
        return redirect("rescue:case-list")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Tài khoản của bạn đã được tạo.")
            return redirect("rescue:case-list")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    context = {
        "reported_count": request.user.reported_rescue_cases.count(),
        "assignment_count": request.user.rescue_assignments.filter(
            is_active=True
        ).count(),
        "organization_count": request.user.organization_memberships.filter(
            is_active=True
        ).count(),
    }
    return render(request, "accounts/profile.html", context)


@support_operator_required
def collaborator_dashboard(request):
    active_statuses = (
        RescueCase.Status.REPORTED,
        RescueCase.Status.VERIFIED,
        RescueCase.Status.ASSIGNED,
        RescueCase.Status.IN_PROGRESS,
    )
    conversations = SupportConversation.objects.annotate(
        unread_count=Count(
            "messages",
            filter=Q(
                messages__sender_role=SupportMessage.SenderRole.USER,
                messages__is_read_by_admin=False,
            ),
        )
    )
    if not request.user.is_superuser:
        conversations = conversations.filter(
            Q(assigned_to__isnull=True) | Q(assigned_to=request.user)
        )

    context = {
        "active_cases": RescueCase.objects.filter(status__in=active_statuses)
        .select_related("organization", "reporter")
        .order_by("-reported_at")[:12],
        "reported_count": RescueCase.objects.filter(
            status=RescueCase.Status.REPORTED
        ).count(),
        "open_conversation_count": conversations.exclude(
            status=SupportConversation.Status.CLOSED
        ).count(),
        "unread_message_count": SupportMessage.objects.filter(
            conversation__in=conversations,
            sender_role=SupportMessage.SenderRole.USER,
            is_read_by_admin=False,
        ).count(),
        "recent_notifications": Notification.objects.filter(
            recipient=request.user
        )[:8],
        "recent_conversations": conversations.select_related("user").order_by(
            "-last_message_at"
        )[:6],
    }
    return render(request, "accounts/collaborator_dashboard.html", context)
