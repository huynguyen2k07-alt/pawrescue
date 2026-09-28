import mimetypes

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from accounts.permissions import is_support_operator, support_operator_ids
from organizations.models import OrganizationMembership, RescueOrganization

from .forms import (
    CaseStatusUpdateForm,
    ClaimOrganizationForm,
    CommunityFeedbackForm,
    RescueAssignmentForm,
    RescueCaseForm,
    RescueUpdateForm,
)
from .geography import DA_NANG_BOUNDS, is_within_da_nang
from .models import (
    ContributorProfile,
    KnowledgeArticle,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseImage,
    RescueUpdateImage,
    RescueUpdateImage,
)
from .notifications import (
    case_participant_ids,
    create_case_notifications,
    create_notifications,
)


MANAGER_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.MANAGER,
)

ACTIVE_CASE_STATUSES = (
    RescueCase.Status.REPORTED,
    RescueCase.Status.VERIFIED,
    RescueCase.Status.ASSIGNED,
    RescueCase.Status.IN_PROGRESS,
)

TERMINAL_CASE_STATUSES = {
    RescueCase.Status.RESCUED,
    RescueCase.Status.CLOSED,
    RescueCase.Status.CANCELLED,
}

PUBLIC_STATUS_FILTERS = (
    (RescueCase.Status.VERIFIED, "Đã xác nhận"),
    (RescueCase.Status.RESCUED, "Đã cứu thành công"),
    (RescueCase.Status.CANCELLED, "Đã hủy"),
)


def _manager_organizations(user):
    if not user.is_authenticated:
        return RescueOrganization.objects.none()
    if user.is_superuser:
        return RescueOrganization.objects.filter(
            is_active=True,
            is_verified=True,
        )
    return RescueOrganization.objects.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__role__in=MANAGER_ROLES,
        is_active=True,
        is_verified=True,
        is_system=False,
    ).distinct()


def _can_review_reported_cases(user):
    """Operators and verified organization managers may triage new reports."""
    if not user.is_authenticated:
        return False
    if is_support_operator(user):
        return True
    return _manager_organizations(user).exists()


def _visible_cases_for(user, queryset):
    """Keep unverified reports private while preserving the triage workflow."""
    if not user.is_authenticated:
        return queryset.exclude(status=RescueCase.Status.REPORTED)
    if _can_review_reported_cases(user):
        return queryset
    return queryset.filter(
        ~Q(status=RescueCase.Status.REPORTED) | Q(reporter=user)
    )


def _can_manage_case(user, rescue_case):
    if not user.is_authenticated or rescue_case.organization_id is None:
        return False
    if user.is_superuser:
        return True
    return OrganizationMembership.objects.filter(
        organization=rescue_case.organization,
        organization__is_active=True,
        organization__is_verified=True,
        organization__is_system=False,
        user=user,
        is_active=True,
        role__in=MANAGER_ROLES,
    ).exists()


def _has_operational_organization(rescue_case):
    if rescue_case.organization_id is None:
        return False
    organization = rescue_case.organization
    return organization.is_active and organization.is_verified


def _can_add_case_update(user, rescue_case):
    if _can_manage_case(user, rescue_case):
        return True
    if not user.is_authenticated or not _has_operational_organization(rescue_case):
        return False
    return rescue_case.assignments.filter(
        assignee=user,
        is_active=True,
    ).exists()


def _can_view_contact(user, rescue_case):
    if not user.is_authenticated:
        return False
    if is_support_operator(user) or rescue_case.reporter_id == user.id:
        return True
    if _can_manage_case(user, rescue_case):
        return True
    if not _has_operational_organization(rescue_case):
        return False
    return rescue_case.assignments.filter(assignee=user, is_active=True).exists()


def _can_view_exact_location(user, rescue_case, manager_organization_ids=None):
    if not rescue_case.is_location_private:
        return True
    if not user.is_authenticated:
        return False
    if is_support_operator(user) or rescue_case.reporter_id == user.id:
        return True
    if manager_organization_ids is not None:
        if rescue_case.organization_id in manager_organization_ids:
            return True
    elif _can_manage_case(user, rescue_case):
        return True
    if not _has_operational_organization(rescue_case):
        return False
    return any(
        assignment.assignee_id == user.id and assignment.is_active
        for assignment in rescue_case.assignments.all()
    )


def _display_coordinates(user, rescue_case, manager_organization_ids=None):
    if rescue_case.latitude is None or rescue_case.longitude is None:
        return None, None, False
    if not is_within_da_nang(rescue_case.latitude, rescue_case.longitude):
        return None, None, False
    can_view_exact = _can_view_exact_location(
        user,
        rescue_case,
        manager_organization_ids,
    )
    latitude = float(rescue_case.latitude)
    longitude = float(rescue_case.longitude)
    if can_view_exact:
        return latitude, longitude, False
    return round(latitude, 2), round(longitude, 2), True


def _private_image_response(field_file):
    try:
        file_handle = field_file.open("rb")
    except (FileNotFoundError, OSError) as error:
        raise Http404 from error
    content_type = mimetypes.guess_type(field_file.name)[0] or "application/octet-stream"
    response = FileResponse(file_handle, content_type=content_type)
    response.headers["Content-Disposition"] = content_disposition_header(
        False,
        field_file.name.rsplit("/", 1)[-1],
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def case_image(request, pk):
    item = get_object_or_404(
        RescueCaseImage.objects.select_related("rescue_case"),
        pk=pk,
    )
    if not _visible_cases_for(
        request.user,
        RescueCase.objects.filter(pk=item.rescue_case_id),
    ).exists():
        raise Http404
    return _private_image_response(item.image)


@require_GET
def update_image(request, pk):
    item = get_object_or_404(
        RescueUpdateImage.objects.select_related("update__rescue_case"),
        pk=pk,
    )
    rescue_case = item.update.rescue_case
    if not _visible_cases_for(
        request.user,
        RescueCase.objects.filter(pk=rescue_case.pk),
    ).exists():
        raise Http404
    return _private_image_response(item.image)


def case_list(request):
    visible_cases = _visible_cases_for(request.user, RescueCase.objects.all())
    cases = visible_cases.select_related(
        "organization",
        "reporter",
    ).prefetch_related("images")

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    animal_type = request.GET.get("animal_type", "").strip()

    if status in {value for value, _label in PUBLIC_STATUS_FILTERS}:
        cases = cases.filter(status=status)
    else:
        status = ""
        cases = cases.filter(status__in=ACTIVE_CASE_STATUSES)

    if query:
        cases = cases.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(address__icontains=query)
        )
    if animal_type in RescueCase.AnimalType.values:
        cases = cases.filter(animal_type=animal_type)

    summary = visible_cases.aggregate(
        active=Count(
            "id",
            filter=Q(
                status__in=ACTIVE_CASE_STATUSES,
            ),
        ),
        verified=Count("id", filter=Q(status=RescueCase.Status.VERIFIED)),
        critical=Count(
            "id",
            filter=Q(
                urgency=RescueCase.Urgency.CRITICAL,
                status__in=ACTIVE_CASE_STATUSES,
            ),
        ),
        rescued=Count("id", filter=Q(status=RescueCase.Status.RESCUED)),
        cancelled=Count("id", filter=Q(status=RescueCase.Status.CANCELLED)),
    )

    rescued_cases = (
        RescueCase.objects.filter(status=RescueCase.Status.RESCUED)
        .select_related("organization", "reporter")
        .prefetch_related("images")
        .order_by("-closed_at", "-updated_at")[:3]
    )

    list_copy = {
        RescueCase.Status.VERIFIED: (
            "Các ca đã xác nhận",
            "Những tin báo đã được quản trị viên kiểm tra và xác nhận.",
        ),
        RescueCase.Status.RESCUED: (
            "Các ca đã cứu thành công",
            "Hồ sơ kết quả cứu hộ được lưu lại minh bạch trên PawRescue.",
        ),
        RescueCase.Status.CANCELLED: (
            "Các ca đã hủy",
            "Những tin báo đã được đóng do trùng lặp hoặc không còn phù hợp.",
        ),
    }
    list_title, list_description = list_copy.get(
        status,
        (
            "Các ca đang cần hỗ trợ",
            "Ưu tiên những ca khẩn cấp và chưa hoàn tất cứu hộ.",
        ),
    )

    feedback_initial = {}
    if request.user.is_authenticated:
        feedback_initial = {
            "name": request.user.full_name,
            "email": request.user.email,
        }
    feedback_form = CommunityFeedbackForm(initial=feedback_initial)
    if request.method == "POST":
        feedback_form = CommunityFeedbackForm(request.POST)
        if feedback_form.is_valid():
            feedback = feedback_form.save(commit=False)
            if request.user.is_authenticated:
                feedback.user = request.user
            feedback.save()
            create_notifications(
                recipient_ids=support_operator_ids(get_user_model()),
                kind=Notification.Kind.FEEDBACK_RECEIVED,
                title="Có góp ý mới từ cộng đồng",
                message=(
                    f"{feedback.name} vừa gửi góp ý thuộc chủ đề "
                    f'“{feedback.get_category_display()}”.'
                ),
                actor=request.user if request.user.is_authenticated else None,
                target_url=reverse("collaborators:dashboard"),
            )
            messages.success(
                request,
                "Cảm ơn bạn! Góp ý đã được gửi tới quản trị viên.",
            )
            return redirect(f"{reverse('rescue:case-list')}#feedback")

    page_obj = Paginator(cases, 9).get_page(request.GET.get("page"))
    context = {
        "page_obj": page_obj,
        "query": query,
        "selected_status": status,
        "selected_animal_type": animal_type,
        "status_choices": PUBLIC_STATUS_FILTERS,
        "animal_type_choices": RescueCase.AnimalType.choices,
        "summary": summary,
        "rescued_cases": rescued_cases,
        "list_title": list_title,
        "list_description": list_description,
        "knowledge_articles": KnowledgeArticle.objects.filter(
            is_published=True
        )[:4],
        "contributors": ContributorProfile.objects.filter(is_active=True)[:4],
        "feedback_form": feedback_form,
    }
    return render(request, "rescue/case_list.html", context)


def knowledge_list(request):
    published_articles = KnowledgeArticle.objects.filter(is_published=True)
    category = request.GET.get("category", "").strip()
    articles = published_articles
    if category in KnowledgeArticle.Category.values:
        articles = articles.filter(category=category)
    else:
        category = ""

    featured_article = articles.filter(is_featured=True).first()
    if featured_article is None:
        featured_article = articles.first()
    article_cards = articles
    if featured_article is not None:
        article_cards = articles.exclude(pk=featured_article.pk)

    category_filters = [
        {
            "value": value,
            "label": label,
            "count": published_articles.filter(category=value).count(),
        }
        for value, label in KnowledgeArticle.Category.choices
    ]
    return render(
        request,
        "rescue/knowledge_list.html",
        {
            "articles": article_cards,
            "featured_article": featured_article,
            "category_filters": category_filters,
            "selected_category": category,
            "published_article_count": published_articles.count(),
        },
    )


def knowledge_detail(request, slug):
    article = get_object_or_404(
        KnowledgeArticle,
        slug=slug,
        is_published=True,
    )
    related_articles = KnowledgeArticle.objects.filter(
        is_published=True,
        category=article.category,
    ).exclude(pk=article.pk)[:3]
    return render(
        request,
        "rescue/knowledge_detail.html",
        {"article": article, "related_articles": related_articles},
    )


def team(request):
    contributors = ContributorProfile.objects.filter(is_active=True)
    return render(
        request,
        "rescue/team.html",
        {
            "contributors": contributors,
            "contributor_count": contributors.count(),
        },
    )


def case_detail(request, pk):
    rescue_case = get_object_or_404(
        _visible_cases_for(request.user, RescueCase.objects.all()).select_related(
            "organization",
            "reporter",
            "adoption_profile",
        ).prefetch_related(
            "images",
            "assignments__assignee",
            "status_history__changed_by",
            "updates__author",
            "updates__images",
        ),
        pk=pk,
    )
    can_manage = _can_manage_case(request.user, rescue_case)
    manager_organizations = _manager_organizations(request.user)
    can_claim = (
        rescue_case.organization_id is None
        and rescue_case.status not in TERMINAL_CASE_STATUSES
        and manager_organizations.exists()
    )
    map_latitude, map_longitude, map_is_approximate = _display_coordinates(
        request.user,
        rescue_case,
    )
    timeline_items = [
        {
            "type": "status",
            "timestamp": history.changed_at,
            "history": history,
        }
        for history in rescue_case.status_history.all()
    ]
    timeline_items.extend(
        {
            "type": "update",
            "timestamp": update.created_at,
            "update": update,
        }
        for update in rescue_case.updates.all()
    )
    timeline_items.sort(key=lambda item: item["timestamp"], reverse=True)
    can_add_update = _can_add_case_update(request.user, rescue_case)
    adoption_profile = getattr(rescue_case, "adoption_profile", None)

    context = {
        "case": rescue_case,
        "can_manage": can_manage,
        "can_claim": can_claim,
        "can_view_contact": _can_view_contact(request.user, rescue_case),
        "can_view_location": _can_view_exact_location(request.user, rescue_case),
        "map_latitude": map_latitude,
        "map_longitude": map_longitude,
        "map_is_approximate": map_is_approximate,
        "timeline_items": timeline_items,
        "can_add_update": can_add_update,
        "update_form": RescueUpdateForm() if can_add_update else None,
        "adoption_profile": adoption_profile,
        "can_create_adoption_profile": (
            can_manage
            and adoption_profile is None
            and rescue_case.status
            in {RescueCase.Status.RESCUED, RescueCase.Status.CLOSED}
        ),
        "status_form": CaseStatusUpdateForm(current_status=rescue_case.status),
        "assignment_form": RescueAssignmentForm(
            organization=rescue_case.organization
        ),
        "claim_form": ClaimOrganizationForm(user=request.user),
        "maptiler_api_key": settings.MAPTILER_API_KEY,
    }
    return render(request, "rescue/case_detail.html", context)


def case_map(request):
    cases = (
        _visible_cases_for(request.user, RescueCase.objects.all()).filter(
            status__in=(
                RescueCase.Status.REPORTED,
                RescueCase.Status.VERIFIED,
                RescueCase.Status.ASSIGNED,
                RescueCase.Status.IN_PROGRESS,
            ),
            latitude__isnull=False,
            longitude__isnull=False,
            latitude__gte=DA_NANG_BOUNDS["south"],
            latitude__lte=DA_NANG_BOUNDS["north"],
            longitude__gte=DA_NANG_BOUNDS["west"],
            longitude__lte=DA_NANG_BOUNDS["east"],
        )
        .select_related("organization", "reporter")
        .prefetch_related("images", "assignments")
    )
    manager_organization_ids = set(
        _manager_organizations(request.user).values_list("id", flat=True)
    )
    map_cases = []
    for rescue_case in cases:
        latitude, longitude, is_approximate = _display_coordinates(
            request.user,
            rescue_case,
            manager_organization_ids,
        )
        images = list(rescue_case.images.all())
        map_cases.append(
            {
                "id": rescue_case.pk,
                "title": rescue_case.title,
                "latitude": latitude,
                "longitude": longitude,
                "is_approximate": is_approximate,
                "address": (
                    "Khu vực gần đúng · Địa chỉ được bảo vệ"
                    if is_approximate
                    else rescue_case.address
                ),
                "animal_type": rescue_case.get_animal_type_display(),
                "animal_type_value": rescue_case.animal_type,
                "urgency": rescue_case.get_urgency_display(),
                "urgency_value": rescue_case.urgency,
                "status": rescue_case.get_status_display(),
                "status_value": rescue_case.status,
                "organization": (
                    rescue_case.organization.name
                    if rescue_case.organization
                    else "Chờ tiếp nhận"
                ),
                "detail_url": reverse(
                    "rescue:case-detail",
                    args=(rescue_case.pk,),
                ),
                "image_url": (
                    reverse("rescue:case-image", args=(images[0].pk,))
                    if images
                    else ""
                ),
            }
        )

    context = {
        "map_cases": map_cases,
        "status_choices": RescueCase.Status.choices,
        "animal_type_choices": RescueCase.AnimalType.choices,
        "maptiler_api_key": settings.MAPTILER_API_KEY,
    }
    return render(request, "rescue/case_map.html", context)


@login_required
def case_create(request):
    if request.method == "POST":
        form = RescueCaseForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                rescue_case = form.save(commit=False)
                rescue_case.reporter = request.user
                rescue_case.save()
                for image in form.cleaned_data["images"]:
                    RescueCaseImage.objects.create(
                        rescue_case=rescue_case,
                        image=image,
                        uploaded_by=request.user,
                    )
                create_notifications(
                    recipient_ids=support_operator_ids(get_user_model()),
                    rescue_case=rescue_case,
                    kind=Notification.Kind.CASE_REPORTED,
                    title="Có tin báo cứu hộ mới",
                    message=(
                        f'{request.user.full_name} vừa báo ca "{rescue_case.title}" '
                        f"tại {rescue_case.address}."
                    ),
                    actor=request.user,
                    target_url=reverse(
                        "rescue:case-detail",
                        args=(rescue_case.pk,),
                    ),
                )

            messages.success(
                request,
                "Tin báo đã được gửi. Các tổ chức cứu hộ có thể tiếp nhận ngay.",
            )
            return redirect("rescue:case-detail", pk=rescue_case.pk)
    else:
        form = RescueCaseForm(
            initial={
                "contact_name": request.user.full_name,
                "contact_phone": request.user.phone,
            }
        )

    return render(
        request,
        "rescue/case_form.html",
        {
            "form": form,
            "maptiler_api_key": settings.MAPTILER_API_KEY,
        },
    )


@login_required
def my_cases(request):
    cases = (
        RescueCase.objects.filter(reporter=request.user)
        .select_related("organization")
        .prefetch_related("images")
    )
    return render(request, "rescue/my_cases.html", {"cases": cases})


@login_required
def notification_list(request):
    selected_filter = request.GET.get("filter", "all")
    if selected_filter not in {"all", "unread"}:
        selected_filter = "all"

    notifications = Notification.objects.filter(
        recipient=request.user,
    ).select_related("actor", "rescue_case")
    if selected_filter == "unread":
        notifications = notifications.filter(is_read=False)

    page_obj = Paginator(notifications, 20).get_page(request.GET.get("page"))
    context = {
        "page_obj": page_obj,
        "selected_filter": selected_filter,
        "total_count": Notification.objects.filter(recipient=request.user).count(),
        "unread_count": Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count(),
    }
    return render(request, "rescue/notification_list.html", context)


@require_POST
@login_required
def notification_open(request, pk):
    notification = get_object_or_404(
        Notification,
        pk=pk,
        recipient=request.user,
    )
    notification.mark_as_read()
    if notification.target_url and url_has_allowed_host_and_scheme(
        notification.target_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(notification.target_url)
    if notification.rescue_case_id:
        return redirect("rescue:case-detail", pk=notification.rescue_case_id)
    return redirect("rescue:notification-list")


@require_POST
@login_required
def notification_read_all(request):
    Notification.objects.filter(
        recipient=request.user,
        is_read=False,
    ).update(is_read=True, read_at=timezone.now())
    messages.success(request, "Đã đánh dấu tất cả thông báo là đã đọc.")
    return redirect("rescue:notification-list")


@require_POST
@login_required
def case_add_update(request, pk):
    rescue_case = get_object_or_404(RescueCase, pk=pk)
    if not _can_add_case_update(request.user, rescue_case):
        return HttpResponseForbidden("Bạn không được phân công cập nhật ca này.")

    form = RescueUpdateForm(request.POST, request.FILES)
    if not form.is_valid():
        error_message = " ".join(
            str(error)
            for field_errors in form.errors.values()
            for error in field_errors
        )
        messages.error(
            request,
            error_message or "Không thể lưu cập nhật. Hãy kiểm tra lại nội dung.",
        )
        return redirect("rescue:case-detail", pk=pk)

    with transaction.atomic():
        rescue_update = form.save(commit=False)
        rescue_update.rescue_case = rescue_case
        rescue_update.author = request.user
        rescue_update.save()
        for image in form.cleaned_data["images"]:
            RescueUpdateImage.objects.create(
                update=rescue_update,
                image=image,
            )
        create_case_notifications(
            recipient_ids=case_participant_ids(rescue_case),
            rescue_case=rescue_case,
            kind=Notification.Kind.CASE_UPDATED,
            title="Có cập nhật mới từ đội cứu hộ",
            message=(
                f'Ca "{rescue_case.title}" vừa có nhật ký hiện trường mới: '
                f"{rescue_update.note[:180]}"
            ),
            actor=request.user,
        )

    messages.success(request, "Đã thêm cập nhật vào nhật ký cứu hộ.")
    return redirect("rescue:case-detail", pk=pk)


@require_POST
@login_required
def case_claim(request, pk):
    form = ClaimOrganizationForm(request.POST, user=request.user)
    if not form.is_valid():
        messages.error(request, "Bạn không có quyền tiếp nhận ca cho tổ chức này.")
        return redirect("rescue:case-detail", pk=pk)

    with transaction.atomic():
        rescue_case = get_object_or_404(
            RescueCase.objects.select_for_update(),
            pk=pk,
        )
        if rescue_case.organization_id is not None:
            messages.info(request, "Ca này đã được một tổ chức khác tiếp nhận.")
            return redirect("rescue:case-detail", pk=pk)
        if rescue_case.status in TERMINAL_CASE_STATUSES:
            messages.error(request, "Ca đã kết thúc nên không thể tiếp nhận.")
            return redirect("rescue:case-detail", pk=pk)

        organization = _manager_organizations(request.user).filter(
            pk=form.cleaned_data["organization"].pk,
        ).first()
        if organization is None:
            messages.error(
                request,
                "Tổ chức chưa được xác minh hoặc bạn không còn quyền tiếp nhận.",
            )
            return redirect("rescue:case-detail", pk=pk)
        rescue_case.organization = organization
        rescue_case.save(update_fields=("organization", "updated_at"))
        if rescue_case.status == RescueCase.Status.REPORTED:
            rescue_case.change_status(
                RescueCase.Status.VERIFIED,
                changed_by=request.user,
                note="Tổ chức đã tiếp nhận và xác minh tin báo.",
            )
        create_case_notifications(
            recipient_ids=(rescue_case.reporter_id,),
            rescue_case=rescue_case,
            kind=Notification.Kind.CASE_CLAIMED,
            title="Ca cứu hộ đã được tiếp nhận",
            message=(
                f'{organization.name} đã tiếp nhận ca "{rescue_case.title}" '
                "và đang điều phối đội cứu hộ."
            ),
            actor=request.user,
        )

    messages.success(request, "Tổ chức của bạn đã tiếp nhận ca cứu hộ.")
    return redirect("rescue:case-detail", pk=pk)


@require_POST
@login_required
def case_update_status(request, pk):
    rescue_case = get_object_or_404(RescueCase, pk=pk)
    if not _can_manage_case(request.user, rescue_case):
        return HttpResponseForbidden("Bạn không có quyền cập nhật ca này.")

    form = CaseStatusUpdateForm(
        request.POST,
        current_status=rescue_case.status,
    )
    if form.is_valid():
        with transaction.atomic():
            history = rescue_case.change_status(
                form.cleaned_data["status"],
                changed_by=request.user,
                note=form.cleaned_data["note"],
            )
            if history is not None:
                note = form.cleaned_data["note"].strip()
                notification_message = (
                    f'Ca "{rescue_case.title}" đã chuyển sang trạng thái '
                    f'“{rescue_case.get_status_display()}”.'
                )
                if note:
                    notification_message += f" Ghi chú: {note}"
                create_case_notifications(
                    recipient_ids=case_participant_ids(rescue_case),
                    rescue_case=rescue_case,
                    kind=Notification.Kind.STATUS_CHANGED,
                    title="Trạng thái ca cứu hộ đã thay đổi",
                    message=notification_message,
                    actor=request.user,
                )
        messages.success(request, "Trạng thái ca cứu hộ đã được cập nhật.")
    else:
        messages.error(request, "Trạng thái mới không hợp lệ.")

    return redirect("rescue:case-detail", pk=pk)


@require_POST
@login_required
def case_assign(request, pk):
    rescue_case = get_object_or_404(RescueCase, pk=pk)
    if not _can_manage_case(request.user, rescue_case):
        return HttpResponseForbidden("Bạn không có quyền phân công ca này.")

    form = RescueAssignmentForm(
        request.POST,
        organization=rescue_case.organization,
    )
    if form.is_valid():
        assignee = form.cleaned_data["assignee"]
        if RescueAssignment.objects.filter(
            rescue_case=rescue_case,
            assignee=assignee,
        ).exists():
            messages.info(request, "Thành viên này đã được phân công cho ca cứu hộ.")
        else:
            with transaction.atomic():
                assignment = form.save(commit=False)
                assignment.rescue_case = rescue_case
                assignment.assigned_by = request.user
                assignment.save()
                if rescue_case.status in {
                    RescueCase.Status.REPORTED,
                    RescueCase.Status.VERIFIED,
                }:
                    rescue_case.change_status(
                        RescueCase.Status.ASSIGNED,
                        changed_by=request.user,
                        note=f"Đã phân công cho {assignee}.",
                    )
                create_case_notifications(
                    recipient_ids=(assignee.pk, rescue_case.reporter_id),
                    rescue_case=rescue_case,
                    kind=Notification.Kind.CASE_ASSIGNED,
                    title="Ca cứu hộ đã được phân công",
                    message=(
                        f'{assignee.full_name or assignee.email} đã được phân công '
                        f'xử lý ca "{rescue_case.title}".'
                    ),
                    actor=request.user,
                )
            messages.success(request, "Đã phân công thành viên cứu hộ.")
    else:
        messages.error(request, "Không thể phân công. Hãy kiểm tra lại thành viên.")

    return redirect("rescue:case-detail", pk=pk)
