from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import redirect, render

from rescue.models import RescueCase
from rescue.permissions import is_rescue_admin
from rescue.notifications import available_notifications
from support.models import SupportConversation, SupportMessage

from .forms import RegistrationForm
from .permissions import is_support_operator


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


@login_required
def collaborator_dashboard(request):
    if not is_support_operator(request.user) and not request.user.rescue_assignments.filter(is_active=True).exists():
        raise PermissionDenied("Bạn chưa được phân công vào ca cứu hộ nào.")
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

    cases = RescueCase.objects.all()
    if not is_rescue_admin(request.user):
        cases = cases.filter(assignments__assignee=request.user, assignments__is_active=True).distinct()

    context = {
        "active_cases": cases.filter(status__in=active_statuses)
        .select_related("organization", "reporter")
        .order_by("-reported_at")[:12],
        "reported_count": (
            cases.filter(status=RescueCase.Status.REPORTED).count()
            if is_rescue_admin(request.user)
            else cases.filter(status__in=active_statuses).count()
        ),
        "open_conversation_count": conversations.exclude(
            status=SupportConversation.Status.CLOSED
        ).count(),
        "unread_message_count": SupportMessage.objects.filter(
            conversation__in=conversations,
            sender_role=SupportMessage.SenderRole.USER,
            is_read_by_admin=False,
        ).count(),
        "recent_notifications": available_notifications(request.user)[:8],
        "recent_conversations": conversations.select_related("user").order_by(
            "-last_message_at"
        )[:6],
    }
    return render(request, "accounts/collaborator_dashboard.html", context)
