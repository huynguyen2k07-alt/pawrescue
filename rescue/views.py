import mimetypes
from urllib.parse import quote, urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.vary import vary_on_cookie

from organizations.permissions import (
    managed_organizations as _manager_organizations,
)
from organizations.models import RescueOrganization

from .forms import (
    CaseHandoffForm,
    CaseStatusUpdateForm,
    ClaimOrganizationForm,
    CommunityFeedbackForm,
    RescueAssignmentForm,
    RescueCaseForm,
    RescueCaseMessageForm,
    RescueUpdateForm,
)
from .geography import DA_NANG_BOUNDS, is_within_da_nang
from .models import (
    CaseStatusHistory,
    ContributorProfile,
    KnowledgeArticle,
    Notification,
    RescueAssignment,
    RescueCase,
    RescueCaseImage,
    RescueCaseMessage,
    RescueUpdateImage,
)
from .notifications import (
    available_notifications,
    case_participant_ids,
    create_case_notifications,
    create_notifications,
)
from .notification_live import notification_destination, notification_snapshot
from .permissions import (
    can_review_case, is_case_assignee, is_rescue_admin,
    is_rescue_moderator, visible_cases_for,
)
from .services import system_rescue_organization
from .statistics import get_public_rescue_statistics


ACTIVE_CASE_STATUSES = (
    RescueCase.Status.REPORTED,
    RescueCase.Status.VERIFIED,
    RescueCase.Status.ASSIGNED,
    RescueCase.Status.IN_PROGRESS,
    RescueCase.Status.PENDING_REVIEW,
)

TERMINAL_CASE_STATUSES = {
    RescueCase.Status.RESCUED,
    RescueCase.Status.CLOSED,
    RescueCase.Status.CANCELLED,
}

PUBLIC_STATUS_FILTERS = (
    (RescueCase.Status.REPORTED, "Chờ xác nhận"),
    (RescueCase.Status.VERIFIED, "Đã phê duyệt"),
    (RescueCase.Status.RESCUED, "Đã cứu thành công"),
    (RescueCase.Status.CANCELLED, "Đã hủy"),
)


def _visible_cases_for(user, queryset):
    return visible_cases_for(user, queryset)


def _can_manage_case(user, rescue_case):
    return is_rescue_admin(user)


def _can_add_case_update(user, rescue_case):
    return rescue_case.status not in TERMINAL_CASE_STATUSES and (
        is_rescue_admin(user) or (
            rescue_case.status != RescueCase.Status.PENDING_REVIEW
            and is_case_assignee(user, rescue_case)
        )
    )


def _can_view_contact(user, rescue_case):
    if not user.is_authenticated:
        return False
    if is_rescue_admin(user) or rescue_case.reporter_id == user.id:
        return True
    return is_case_assignee(user, rescue_case)


def _can_view_exact_location(user, rescue_case, manager_organization_ids=None):
    if not rescue_case.is_location_private:
        return True
    if not user.is_authenticated:
        return False
    if is_rescue_admin(user) or rescue_case.reporter_id == user.id:
        return True
    return is_case_assignee(user, rescue_case)


def _form_error_message(form):
    return " ".join(
        str(error)
        for field_errors in form.errors.values()
        for error in field_errors
    )


def _handoff_email_url(rescue_case):
    organization = rescue_case.organization
    if organization is None or organization.is_system or not organization.email:
        return ""

    body = (
        f"Kính gửi {organization.name},\n\n"
        f"PawRescue chuyển yêu cầu cứu hộ #{rescue_case.pk}: {rescue_case.title}.\n"
        f"Tình trạng: {rescue_case.description}\n"
        f"Địa chỉ: {rescue_case.address}\n"
        f"Tọa độ: {rescue_case.latitude}, {rescue_case.longitude}\n"
        f"Liên hệ hiện trường: {rescue_case.contact_name} - {rescue_case.contact_phone}\n\n"
        "Nhờ đơn vị xác nhận tiếp nhận và phản hồi kết quả xử lý.\nTrân trọng, PawRescue."
    )
    email_query = urlencode(
        {
            "subject": f"PawRescue bàn giao yêu cầu cứu hộ #{rescue_case.pk}",
            "body": body,
        },
        quote_via=quote,
    )
    recipient = quote(organization.email, safe="@.")
    return f"mailto:{recipient}?{email_query}"


def _display_coordinates(user, rescue_case, manager_organization_ids=None):
    # Vị trí riêng tư được hiển thị gần đúng khi người xem không có quyền biết tọa độ chính xác.
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


def _google_maps_url(latitude, longitude):
    if latitude is None or longitude is None:
        return ""
    query = urlencode({"api": "1", "query": f"{latitude},{longitude}"})
    return f"https://www.google.com/maps/search/?{query}"


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
    # Kiểm tra quyền xem ca trước khi cung cấp ảnh hiện trường từ kho riêng tư.
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

    approved_statuses = tuple(
        value for value in ACTIVE_CASE_STATUSES if value != RescueCase.Status.REPORTED
    )
    cancelled_statuses = (RescueCase.Status.CANCELLED, RescueCase.Status.CLOSED)
    if status not in {value for value, _label in PUBLIC_STATUS_FILTERS}:
        status = RescueCase.Status.VERIFIED
    if status == RescueCase.Status.VERIFIED:
        cases = cases.filter(status__in=approved_statuses)
    elif status == RescueCase.Status.CANCELLED:
        cases = cases.filter(status__in=cancelled_statuses)
    else:
        cases = cases.filter(status=status)

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
        reported=Count("id", filter=Q(status=RescueCase.Status.REPORTED)),
        verified=Count("id", filter=Q(status__in=approved_statuses)),
        critical=Count(
            "id",
            filter=Q(
                urgency=RescueCase.Urgency.CRITICAL,
                status__in=ACTIVE_CASE_STATUSES,
            ),
        ),
        rescued=Count("id", filter=Q(status=RescueCase.Status.RESCUED)),
        cancelled=Count("id", filter=Q(status__in=cancelled_statuses)),
    )

    rescued_cases = (
        RescueCase.objects.filter(status=RescueCase.Status.RESCUED)
        .select_related("organization", "reporter")
        .prefetch_related("images")
        .order_by("-closed_at", "-updated_at")[:3]
    )

    list_copy = {
        RescueCase.Status.REPORTED: (
            "Các tin đang chờ xác nhận",
            "Request mới nhận, chưa kiểm tra thông tin. Chỉ người liên quan được xem.",
        ),
        RescueCase.Status.VERIFIED: (
            "Các ca đã phê duyệt",
            "Tin đã kiểm tra, đang xử lý hoặc chờ admin duyệt kết quả cuối cùng.",
        ),
        RescueCase.Status.RESCUED: (
            "Các ca đã cứu thành công",
            "Hồ sơ kết quả cứu hộ được lưu lại minh bạch trên PawRescue.",
        ),
        RescueCase.Status.CANCELLED: (
            "Các ca đã hủy",
            "Những tin đã hủy hoặc đóng hồ sơ mà chưa xác nhận cứu thành công.",
        ),
    }
    list_title, list_description = list_copy[status]

    # ===== CHỨC NĂNG CHÍNH: TIẾP NHẬN GÓP Ý =====
    # Lưu góp ý và thông báo riêng cho quản trị viên để theo dõi xử lý.
    feedback_form = CommunityFeedbackForm(
        initial={
            "name": request.user.full_name if request.user.is_authenticated else "",
            "email": request.user.email if request.user.is_authenticated else "",
        }
    )
    if request.method == "POST":
        feedback_form = CommunityFeedbackForm(request.POST)
        if feedback_form.is_valid():
            feedback = feedback_form.save(commit=False)
            if request.user.is_authenticated:
                feedback.user = request.user
            feedback.save()
            create_notifications(
                recipient_ids=get_user_model().objects.filter(
                    is_active=True, is_superuser=True
                ).values_list("pk", flat=True),
                kind=Notification.Kind.FEEDBACK_RECEIVED,
                title="Có góp ý mới từ cộng đồng",
                message=(
                    f"{feedback.name} vừa gửi góp ý thuộc chủ đề "
                    f'“{feedback.get_category_display()}”.'
                ),
                actor=request.user if request.user.is_authenticated else None,
                target_url=reverse("admin:rescue_communityfeedback_change", args=(feedback.pk,)),
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
        "public_statistics": get_public_rescue_statistics(),
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

    category_counts = dict(
        published_articles.values_list("category").annotate(total=Count("pk"))
    )
    category_filters = [
        {
            "value": value,
            "label": label,
            "count": category_counts.get(value, 0),
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
            "published_article_count": sum(category_counts.values()),
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
    contributors = list(ContributorProfile.objects.filter(is_active=True))
    return render(
        request,
        "rescue/team.html",
        {
            "contributors": contributors,
            "contributor_count": len(contributors),
        },
    )


def case_detail(request, pk):
    # ===== CHỨC NĂNG CHÍNH: XEM HỒ SƠ CỨU HỘ =====
    # Hiển thị liên hệ, vị trí chính xác và thao tác xử lý theo quyền của người xem.
    rescue_case = get_object_or_404(
        _visible_cases_for(request.user, RescueCase.objects.all()).select_related(
            "organization",
            "reporter",
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
    is_terminal = rescue_case.status in TERMINAL_CASE_STATUSES
    can_decide = can_manage and not is_terminal
    can_coordinate = can_manage or is_case_assignee(request.user, rescue_case)
    is_pending_review = rescue_case.status == RescueCase.Status.PENDING_REVIEW
    can_moderate = (
        is_rescue_moderator(request.user)
        and can_review_case(request.user, rescue_case)
        and not is_terminal and not is_pending_review
    )
    requested_review = request.GET.get("review")
    review_choices = [
        (RescueCase.Status.CLOSED, "Đóng hồ sơ"),
        (RescueCase.Status.CANCELLED, "Không thể tiếp tục xử lý"),
    ]
    review_status = (
        requested_review
        if requested_review in dict(review_choices)
        else RescueCase.Status.CANCELLED
    )
    status_form = CaseStatusUpdateForm(
        current_status=rescue_case.status,
        initial={"status": review_status},
        auto_id="id_status_%s",
    )
    status_form.fields["status"].choices = review_choices
    status_form.fields["status"].label = "Kết quả xử lý"
    status_form.fields["note"].label = "Đánh giá kết quả"
    completion_form = CaseStatusUpdateForm(
        current_status=rescue_case.status,
        rescue_case=rescue_case,
        initial={"status": RescueCase.Status.RESCUED},
        auto_id="id_complete_%s",
    )
    completion_form.fields["note"].label = "Đánh giá kết quả cứu hộ"
    completion_form.fields["note"].required = True
    completion_form.fields["note"].help_text = (
        "Ghi ngắn gọn việc đã làm và tình trạng động vật sau cứu hộ."
    )
    has_valid_location = (
        bool(rescue_case.address.strip())
        and is_within_da_nang(rescue_case.latitude, rescue_case.longitude)
    )
    can_complete = can_decide and has_valid_location
    can_report_completion = can_moderate and has_valid_location and rescue_case.status in {
        RescueCase.Status.VERIFIED, RescueCase.Status.ASSIGNED,
        RescueCase.Status.IN_PROGRESS,
    }
    completion_report = (
        rescue_case.status_history.filter(to_status=RescueCase.Status.PENDING_REVIEW)
        .select_related("changed_by").order_by("-changed_at", "-pk").first()
        if is_pending_review else None
    )
    admin_notification_count = 0
    has_case_messages = False
    if can_manage:
        admin_notification_count = get_user_model().objects.filter(
            is_active=True, is_superuser=False, role=get_user_model().Role.MODERATOR,
        ).exclude(pk=request.user.pk).count()
        has_case_messages = rescue_case.private_messages.filter(
            Q(sender=request.user) | Q(recipient=request.user)
        ).exists()

    private_assignments = RescueAssignment.objects.none()
    if can_coordinate:
        assignment_filter = {} if can_manage else {"assignee": request.user}
        private_assignments = rescue_case.assignments.filter(**assignment_filter)

    context = {
        "case": rescue_case,
        "can_manage": can_manage,
        "can_claim": can_decide and (
            rescue_case.status == RescueCase.Status.REPORTED
            or rescue_case.organization_id is None
        ),
        "can_decide": can_decide,
        "can_review": can_review_case(request.user, rescue_case),
        "can_moderate": can_moderate,
        "can_report_completion": can_report_completion,
        "is_pending_review": is_pending_review,
        "completion_report": completion_report,
        "google_maps_url": _google_maps_url(map_latitude, map_longitude),
        "can_coordinate": can_coordinate,
        "is_terminal": is_terminal,
        "can_view_contact": _can_view_contact(request.user, rescue_case),
        "can_view_location": _can_view_exact_location(request.user, rescue_case),
        "map_latitude": map_latitude,
        "map_longitude": map_longitude,
        "map_is_approximate": map_is_approximate,
        "timeline_items": timeline_items,
        "can_add_update": can_add_update,
        "update_form": (
            RescueUpdateForm(auto_id="id_update_%s") if can_add_update else None
        ),
        "status_form": status_form,
        "completion_form": completion_form,
        "can_complete": can_complete,
        "admin_notification_count": admin_notification_count,
        "has_admin_recipients": admin_notification_count > 0,
        "has_case_messages": has_case_messages,
        "handoff_form": (
            CaseHandoffForm(auto_id="id_handoff_%s") if can_decide else None
        ),
        "handoff_email_url": _handoff_email_url(rescue_case) if can_manage else "",
        "private_assignments": private_assignments,
        "assignment_form": RescueAssignmentForm(
            organization=rescue_case.organization
        ),
        "claim_form": ClaimOrganizationForm(user=request.user),
        "maptiler_api_key": settings.MAPTILER_API_KEY,
    }
    return render(request, "rescue/case_detail.html", context)


def case_map(request):
    # ===== CHỨC NĂNG CHÍNH: BẢN ĐỒ CA CỨU HỘ THÀNH CÔNG =====
    # Chỉ đưa ca đã chốt cứu thành công vào cả danh sách và dữ liệu bản đồ công khai.
    cases = (
        RescueCase.objects.filter(
            status=RescueCase.Status.RESCUED,
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
    map_cases = []
    for rescue_case in cases:
        latitude, longitude, is_approximate = _display_coordinates(
            request.user,
            rescue_case,
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
                "completed_at_display": (
                    timezone.localtime(rescue_case.closed_at).strftime("%H:%M, %d/%m/%Y")
                    if rescue_case.closed_at else ""
                ),
                "organization": (
                    rescue_case.organization.name
                    if rescue_case.organization
                    else "Chưa ghi nhận đơn vị"
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
        "animal_type_choices": RescueCase.AnimalType.choices,
        "maptiler_api_key": settings.MAPTILER_API_KEY,
    }
    return render(request, "rescue/case_map.html", context)


@login_required
def case_create(request):
    # ===== CHỨC NĂNG CHÍNH: GỬI YÊU CẦU CỨU HỘ =====
    # Lưu tin báo cùng ảnh trong một giao dịch rồi thông báo cho quản trị viên tiếp nhận.
    if request.method == "POST":
        form = RescueCaseForm(
            request.POST, request.FILES, require_location_confirmation=True,
        )
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
                    recipient_ids=get_user_model().objects.filter(
                        is_active=True, is_superuser=True
                    ).values_list("pk", flat=True),
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
                "Tin báo và vị trí đã được gửi tới admin để xác minh và phân công xử lý. "
                f"Mã tin báo: #{rescue_case.pk}.",
            )
            return redirect("rescue:case-detail", pk=rescue_case.pk)
        for field in form:
            if field.errors:
                field.field.widget.attrs["autofocus"] = True
                break
    else:
        form = RescueCaseForm(
            require_location_confirmation=True,
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
            "address_search_enabled": bool(settings.GEOAPIFY_API_KEY),
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

    notifications = available_notifications(request.user).select_related("actor", "rescue_case")
    if selected_filter == "unread":
        notifications = notifications.filter(is_read=False)

    notification_counts = available_notifications(request.user).aggregate(
        total=Count("pk"),
        unread=Count("pk", filter=Q(is_read=False)),
    )
    page_obj = Paginator(notifications, 20).get_page(request.GET.get("page"))
    for notification in page_obj:
        notification.destination_url = notification_destination(notification, request)
    context = {
        "page_obj": page_obj,
        "selected_filter": selected_filter,
        "total_count": notification_counts["total"],
        "unread_count": notification_counts["unread"],
    }
    return render(request, "rescue/notification_list.html", context)


# ===== CHỨC NĂNG CHÍNH: ĐÁNH DẤU THÔNG BÁO NGAY TẠI DANH SÁCH =====
# Trả số đếm mới cho JavaScript; khi tắt JavaScript vẫn quay về đúng bộ lọc và trang đang đọc.
def _notification_read_response(request):
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse(notification_snapshot(request))
    query = {}
    if request.POST.get("filter") == "unread":
        query["filter"] = "unread"
    page = request.POST.get("page", "")
    if page.isascii() and page.isdigit() and 0 < len(page) <= 6 and int(page) > 1:
        query["page"] = page
    url = reverse("rescue:notification-list")
    return redirect(f"{url}?{urlencode(query)}" if query else url)


@never_cache
@vary_on_cookie
@require_POST
@login_required
def notification_open(request, pk):
    notification = get_object_or_404(
        available_notifications(request.user),
        pk=pk,
        recipient=request.user,
    )
    notification.mark_as_read()
    return _notification_read_response(request)


@never_cache
@vary_on_cookie
@require_POST
@login_required
def notification_read_all(request):
    available_notifications(request.user).filter(is_read=False).update(is_read=True, read_at=timezone.now())
    return _notification_read_response(request)


@require_POST
@login_required
def case_add_update(request, pk):
    # ===== CHỨC NĂNG CHÍNH: CẬP NHẬT NHẬT KÝ CỨU HỘ =====
    # Quản trị viên hoặc người còn được phân công mới được ghi nhật ký cho ca chưa chốt.
    rescue_case = get_object_or_404(RescueCase, pk=pk)
    if not _can_add_case_update(request.user, rescue_case):
        return HttpResponseForbidden("Bạn không được phân công cập nhật ca này.")

    form = RescueUpdateForm(request.POST, request.FILES)
    if not form.is_valid():
        error_message = _form_error_message(form)
        messages.error(
            request,
            error_message or "Không thể lưu cập nhật. Hãy kiểm tra lại nội dung.",
        )
        return redirect("rescue:case-detail", pk=pk)

    with transaction.atomic():
        rescue_case = get_object_or_404(RescueCase.objects.select_for_update(), pk=pk)
        if not _can_add_case_update(request.user, rescue_case):
            return HttpResponseForbidden("Ca đã chốt hoặc bạn không còn được phân công cập nhật.")
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
    # ===== CHỨC NĂNG CHÍNH: TIẾP NHẬN YÊU CẦU =====
    # Quản trị viên tiếp nhận tin báo và thông báo cho người gửi sau khi xác minh.
    if not is_rescue_admin(request.user):
        return HttpResponseForbidden("Chỉ admin được tiếp nhận và điều phối ca cứu hộ.")
    organization = None
    if request.POST.get("organization"):
        form = ClaimOrganizationForm(request.POST, user=request.user)
        if not form.is_valid():
            messages.error(request, "Bạn không có quyền tiếp nhận ca cho tổ chức này.")
            return redirect("rescue:case-detail", pk=pk)
        organization = form.cleaned_data["organization"]

    with transaction.atomic():
        rescue_case = get_object_or_404(
            RescueCase.objects.select_for_update(),
            pk=pk,
        )
        if rescue_case.status in TERMINAL_CASE_STATUSES:
            messages.error(request, "Ca đã kết thúc nên không thể tiếp nhận.")
            return redirect("rescue:case-detail", pk=pk)
        needs_organization = rescue_case.organization_id is None
        if not needs_organization and rescue_case.status != RescueCase.Status.REPORTED:
            messages.info(request, "Yêu cầu đã được tiếp nhận trước đó.")
            return redirect("rescue:case-detail", pk=pk)
        if needs_organization:
            if organization is not None:
                organization = _manager_organizations(request.user).filter(pk=organization.pk).first()
                if organization is None:
                    messages.error(request, "Đơn vị không còn đủ điều kiện tiếp nhận.")
                    return redirect("rescue:case-detail", pk=pk)
            else:
                organization = system_rescue_organization(request.user)
            rescue_case.organization = organization
            rescue_case.save(update_fields=("organization", "updated_at"))
        if rescue_case.status == RescueCase.Status.REPORTED:
            rescue_case.change_status(
                RescueCase.Status.VERIFIED,
                changed_by=request.user,
                note="Quản trị viên đã tiếp nhận và xác minh tin báo.",
            )
        create_case_notifications(
            recipient_ids=(rescue_case.reporter_id,),
            rescue_case=rescue_case,
            kind=Notification.Kind.CASE_CLAIMED,
            title="Ca cứu hộ đã được tiếp nhận",
            message=(
                f'{rescue_case.organization.name} đã tiếp nhận ca "{rescue_case.title}" '
                "và đang điều phối đội cứu hộ."
            ),
            actor=request.user,
        )

    messages.success(request, "Đã xác nhận và tiếp nhận yêu cầu cứu hộ.")
    return redirect("rescue:case-detail", pk=pk)


@require_POST
@login_required
def case_handoff(request, pk):
    # ===== CHỨC NĂNG CHÍNH: BÀN GIAO ĐƠN VỊ CỨU HỘ =====
    # Bàn giao cho đơn vị bên ngoài nhưng giữ lịch sử và quyền chốt kết quả ở quản trị viên.
    if not is_rescue_admin(request.user):
        return HttpResponseForbidden("Chỉ quản trị viên được chuyển đơn vị xử lý.")
    with transaction.atomic():
        rescue_case = get_object_or_404(RescueCase.objects.select_for_update(), pk=pk)
        if rescue_case.status in TERMINAL_CASE_STATUSES:
            messages.error(request, "Yêu cầu đã chốt, không thể bàn giao thêm.")
            return redirect("rescue:case-detail", pk=pk)
        form = CaseHandoffForm(request.POST)
        if not form.is_valid():
            messages.error(request, _form_error_message(form))
            return redirect("rescue:case-detail", pk=pk)
        organization = (
            RescueOrganization.objects.select_for_update()
            .filter(
                pk=form.cleaned_data["organization"].pk,
                is_active=True,
                is_verified=True,
                is_system=False,
            )
            .first()
        )
        has_contact = organization is not None and (
            organization.phone.strip() or organization.email.strip()
        )
        if not has_contact:
            messages.error(request, "Đơn vị không còn đủ thông tin hoặc điều kiện tiếp nhận.")
            return redirect("rescue:case-detail", pk=pk)
        if rescue_case.organization_id == organization.pk:
            messages.info(request, "Yêu cầu đã được chuyển cho đơn vị này.")
            return redirect("rescue:case-detail", pk=pk)
        active_assignments = rescue_case.assignments.filter(is_active=True)
        ended_assignee_ids = list(
            active_assignments.values_list("assignee_id", flat=True)
        )
        active_assignments.update(is_active=False, completed_at=timezone.now())
        rescue_case.organization = organization
        rescue_case.save(update_fields=("organization", "updated_at"))
        note = f"Quản trị viên đã chuyển yêu cầu cho đơn vị {organization.name}."
        target_status = (
            RescueCase.Status.IN_PROGRESS
            if rescue_case.status == RescueCase.Status.IN_PROGRESS
            else RescueCase.Status.ASSIGNED
        )
        history = rescue_case.change_status(
            target_status,
            changed_by=request.user,
            note=note,
        )
        if history is None:
            CaseStatusHistory.objects.create(
                rescue_case=rescue_case,
                from_status=rescue_case.status,
                to_status=rescue_case.status,
                changed_by=request.user,
                note=note,
            )
        create_notifications(
            recipient_ids=ended_assignee_ids,
            rescue_case=rescue_case,
            kind=Notification.Kind.CASE_ASSIGNED,
            title="Yêu cầu đã được chuyển đơn vị xử lý",
            message=f"Phân công của bạn ở ca #{pk} đã kết thúc khi quản trị viên chuyển đơn vị xử lý.",
            actor=request.user,
            target_url=reverse("rescue:notification-list"),
        )
        create_case_notifications(
            recipient_ids=(rescue_case.reporter_id,),
            rescue_case=rescue_case,
            kind=Notification.Kind.CASE_ASSIGNED,
            title="Đã chuyển đơn vị cứu hộ",
            message=f'Yêu cầu "{rescue_case.title}" đã được chuyển cho {organization.name}.',
            actor=request.user,
        )
    messages.success(
        request,
        f"Đã ghi nhận bàn giao cho {organization.name}. "
        "Bạn có thể liên hệ đơn vị theo thông tin trong hồ sơ.",
    )
    return redirect("rescue:case-detail", pk=pk)


@require_POST
@login_required
def case_update_status(request, pk):
    # ===== CHỨC NĂNG CHÍNH: ĐÁNH GIÁ VÀ CHỐT CA =====
    # Quản trị viên báo kết quả ca được giao; chỉ admin chính được duyệt thành công và công khai vị trí.
    is_admin = is_rescue_admin(request.user)
    if not (is_admin or is_rescue_moderator(request.user)):
        return HttpResponseForbidden("Bạn không có quyền cập nhật ca này.")
    with transaction.atomic():
        rescue_case = get_object_or_404(RescueCase.objects.select_for_update(), pk=pk)
        if not can_review_case(request.user, rescue_case):
            raise Http404
        if rescue_case.status in TERMINAL_CASE_STATUSES:
            messages.error(request, "Ca đã được admin chốt sổ, không thể đổi lại trạng thái.")
            return redirect("rescue:case-detail", pk=pk)
        requested_status = request.POST.get("status")
        if not is_admin:
            if requested_status not in {
                RescueCase.Status.VERIFIED, RescueCase.Status.PENDING_REVIEW,
            }:
                return HttpResponseForbidden("Quản trị viên chỉ xác minh thông tin hoặc báo hoàn thành cho admin chính.")
            if rescue_case.status == RescueCase.Status.PENDING_REVIEW:
                messages.info(request, "Kết quả đã gửi, đang chờ admin chính duyệt.")
                return redirect("rescue:case-detail", pk=pk)
            if requested_status == rescue_case.status:
                messages.info(request, "Thông tin ca đã được xác nhận trước đó.")
                return redirect("rescue:case-detail", pk=pk)
            allowed_sources = (
                {RescueCase.Status.REPORTED, RescueCase.Status.ASSIGNED}
                if requested_status == RescueCase.Status.VERIFIED
                else {
                    RescueCase.Status.VERIFIED, RescueCase.Status.ASSIGNED,
                    RescueCase.Status.IN_PROGRESS,
                }
            )
            if rescue_case.status not in allowed_sources:
                messages.error(request, "Hãy xác nhận thông tin trước khi báo hoàn thành.")
                return redirect("rescue:case-detail", pk=pk)
        form = CaseStatusUpdateForm(
            request.POST, current_status=rescue_case.status, rescue_case=rescue_case,
        )
        if form.is_valid():
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
            if rescue_case.status == RescueCase.Status.RESCUED:
                messages.success(
                    request,
                    "Đã xử lý thành công. Kết quả và vị trí cứu hộ đã được lưu trên bản đồ.",
                )
            elif rescue_case.status == RescueCase.Status.PENDING_REVIEW:
                messages.success(request, "Đã báo hoàn thành cho admin chính. Ca chỉ lên bản đồ sau khi được duyệt.")
            else:
                messages.success(request, "Đã lưu đánh giá và trạng thái ca cứu hộ.")
        else:
            messages.error(request, _form_error_message(form))

    return redirect("rescue:case-detail", pk=pk)


@require_POST
@login_required
def case_notify_admins(request, pk):
    # ===== CHỨC NĂNG CHÍNH: GỬI TIN TỰ ĐỘNG CHO ADMIN =====
    # Admin chính giao ca và gửi riêng thông tin cho các quản trị viên; không tự xác minh hoặc công khai ca.
    if not is_rescue_admin(request.user):
        return HttpResponseForbidden("Chỉ admin được gửi tin điều phối tự động.")
    with transaction.atomic():
        rescue_case = get_object_or_404(RescueCase.objects.select_for_update(), pk=pk)
        if rescue_case.status in TERMINAL_CASE_STATUSES:
            messages.error(request, "Ca đã chốt sổ nên không gửi thêm yêu cầu xử lý.")
            return redirect("rescue:case-detail", pk=pk)
        recipients = get_user_model().objects.filter(
            is_active=True, is_superuser=False, role=get_user_model().Role.MODERATOR,
        ).exclude(pk=request.user.pk)
        detail_url = reverse("rescue:case-detail", args=(pk,))
        coordinates = (
            f"{rescue_case.latitude}, {rescue_case.longitude}"
            if rescue_case.latitude is not None and rescue_case.longitude is not None
            else "Chưa bổ sung vị trí"
        )
        body = (
            f"[Tự động] Nhờ quản trị viên phối hợp xử lý ca #{pk}: {rescue_case.title}\n"
            f"Động vật: {rescue_case.get_animal_type_display()}\n"
            f"Mức độ: {rescue_case.get_urgency_display()}\n"
            f"Địa chỉ hiện trường: {rescue_case.address[:1200]}\n"
            f"Tọa độ: {coordinates}\n"
            f"Hồ sơ và bản đồ: {detail_url}"
        )
        already_sent_ids = set(
            rescue_case.private_messages.filter(
                sender=request.user, body=body,
            ).values_list("recipient_id", flat=True)
        )
        new_recipient_ids = set(recipients.values_list("pk", flat=True)) - already_sent_ids
        for recipient in recipients:
            assignment, created = RescueAssignment.objects.get_or_create(
                rescue_case=rescue_case, assignee=recipient,
                defaults={"assigned_by": request.user, "notes": "Kiểm tra tin báo và báo kết quả cho admin chính."},
            )
            if not created and not assignment.is_active:
                assignment.is_active = True
                assignment.completed_at = None
                assignment.assigned_by = request.user
                assignment.save(update_fields=("is_active", "completed_at", "assigned_by"))
                new_recipient_ids.add(recipient.pk)
        RescueCaseMessage.objects.bulk_create(
            [
                RescueCaseMessage(
                    rescue_case=rescue_case, sender=request.user,
                    recipient_id=recipient_id, body=body,
                )
                for recipient_id in sorted(new_recipient_ids)
            ]
        )
        create_notifications(
            recipient_ids=new_recipient_ids,
            rescue_case=rescue_case,
            kind=Notification.Kind.CASE_MESSAGE,
            title=f"Cần phối hợp xử lý ca #{pk}",
            message=f'Bạn nhận được thông tin cứu hộ cho ca "{rescue_case.title}".',
            actor=request.user,
            target_url=reverse("rescue:case-messages", args=(pk,)),
        )
        if new_recipient_ids:
            messages.success(
                request, f"Đã gửi tin tự động cho {len(new_recipient_ids)} quản trị viên.",
            )
        else:
            messages.info(
                request, "Không có quản trị viên mới cần nhận tin; nội dung đã gửi sẽ không bị gửi trùng.",
            )
    return redirect("rescue:case-detail", pk=pk)


@login_required
@require_http_methods(("GET", "POST"))
def case_reject(request, pk):
    # ===== CHỨC NĂNG CHÍNH: TỪ CHỐI HỒ SƠ CỨU HỘ =====
    # Chỉ xử lý ca được giao; bắt buộc xác nhận và lý do trước khi xóa, thông báo vẫn giữ cho admin và người báo tin.
    if not (is_rescue_admin(request.user) or is_rescue_moderator(request.user)):
        return HttpResponseForbidden("Bạn không có quyền từ chối hồ sơ.")
    with transaction.atomic():
        rescue_case = get_object_or_404(RescueCase.objects.select_for_update(), pk=pk)
        if not can_review_case(request.user, rescue_case):
            raise Http404
        if rescue_case.status in TERMINAL_CASE_STATUSES or rescue_case.status == RescueCase.Status.PENDING_REVIEW:
            messages.error(request, "Hồ sơ đã chốt hoặc đang chờ admin chính duyệt nên không thể từ chối tại đây.")
            return redirect("rescue:case-detail", pk=pk)
        reason = request.POST.get("reason", "").strip()
        if request.method == "POST" and request.POST.get("confirm") == "yes" and 0 < len(reason) <= 2000:
            recipient_ids = set(get_user_model().objects.filter(
                is_active=True, is_superuser=True,
            ).values_list("pk", flat=True))
            if rescue_case.reporter_id:
                recipient_ids.add(rescue_case.reporter_id)
            title = rescue_case.title
            rescue_case.delete()
            create_notifications(
                recipient_ids=recipient_ids,
                kind=Notification.Kind.STATUS_CHANGED,
                title=f"Hồ sơ cứu hộ #{pk} đã bị từ chối",
                message=f'Hồ sơ "{title}" đã được từ chối và xóa. Lý do: {reason}',
                actor=request.user,
                target_url=reverse("rescue:notification-list"),
            )
            messages.success(request, "Đã từ chối và xóa hồ sơ, đồng thời thông báo cho admin chính và người báo tin.")
            return redirect(
                "admin:rescue_rescuecase_changelist"
                if is_rescue_admin(request.user) else "collaborators:dashboard"
            )
        return render(request, "rescue/case_reject_confirm.html", {
            "case": rescue_case, "reason": reason,
            "reason_error": (
                "Hãy xác nhận xóa và ghi lý do từ 1 đến 2.000 ký tự."
                if request.method == "POST" else ""
            ),
        }, status=400 if request.method == "POST" else 200)


@require_POST
@login_required
def case_assign(request, pk):
    # ===== CHỨC NĂNG CHÍNH: PHÂN CÔNG NGƯỜI PHỤ TRÁCH =====
    # Quản trị viên phân công ca chưa chốt; chỉ dẫn được gửi riêng cho người phụ trách.
    if not is_rescue_admin(request.user):
        return HttpResponseForbidden("Bạn không có quyền phân công ca này.")
    with transaction.atomic():
        rescue_case = get_object_or_404(RescueCase.objects.select_for_update(), pk=pk)
        if rescue_case.status in TERMINAL_CASE_STATUSES:
            messages.error(request, "Ca đã chốt sổ nên không thể phân công thêm.")
            return redirect("rescue:case-detail", pk=pk)
        form = RescueAssignmentForm(request.POST, organization=rescue_case.organization)
        if form.is_valid():
            assignee = form.cleaned_data["assignee"]
            assignment, created = RescueAssignment.objects.get_or_create(
                rescue_case=rescue_case,
                assignee=assignee,
                defaults={"assigned_by": request.user, "notes": form.cleaned_data["notes"]},
            )
            if not created:
                assignment.is_active = True
                assignment.completed_at = None
                assignment.notes = form.cleaned_data["notes"]
                assignment.assigned_by = request.user
                assignment.save(update_fields=("is_active", "completed_at", "notes", "assigned_by"))
            if not is_rescue_moderator(assignee) and rescue_case.status in {
                RescueCase.Status.REPORTED,
                RescueCase.Status.VERIFIED,
            }:
                rescue_case.change_status(
                    RescueCase.Status.ASSIGNED,
                    changed_by=request.user,
                    note="Admin đã xác minh tin báo và phân công người phụ trách.",
                )
            if assignee.pk != request.user.pk:
                RescueCaseMessage.objects.create(
                    rescue_case=rescue_case,
                    sender=request.user,
                    recipient=assignee,
                    body=(
                        f"Bạn được phân công phụ trách ca #{rescue_case.pk}. "
                        "Mở thông tin ca để xem địa chỉ và vị trí trên bản đồ.\n\n"
                        + form.cleaned_data["notes"]
                    ).strip(),
                )
            create_notifications(
                recipient_ids=(assignee.pk,),
                rescue_case=rescue_case,
                kind=Notification.Kind.CASE_ASSIGNED,
                title="Admin đã giao cho bạn một ca cứu hộ",
                message=f'Bạn được phân công xử lý ca "{rescue_case.title}". Mở trao đổi riêng để xem chỉ dẫn.',
                actor=request.user,
                target_url=reverse("rescue:case-messages", args=(pk,)),
            )
            create_case_notifications(
                recipient_ids=(rescue_case.reporter_id,),
                rescue_case=rescue_case,
                kind=Notification.Kind.CASE_ASSIGNED,
                title="Ca cứu hộ đã được phân công",
                message=f'Admin đã phân công người phụ trách ca "{rescue_case.title}".',
                actor=request.user,
            )
            messages.success(request, "Đã phân công. Người phụ trách có thể xem chỉ dẫn và nhắn riêng với admin.")
        else:
            messages.error(request, "Không thể phân công. Hãy chọn người phụ trách đang hoạt động.")

    return redirect("rescue:case-detail", pk=pk)


@login_required
@require_http_methods(("GET", "POST"))
def case_messages(request, pk):
    # ===== CHỨC NĂNG CHÍNH: NHẮN TIN ĐIỀU PHỐI =====
    # Admin chính trao đổi với người được giao ca; chỉ người gửi và nhận được đọc tin.
    rescue_case = get_object_or_404(RescueCase, pk=pk)
    if not (is_rescue_admin(request.user) or is_case_assignee(request.user, rescue_case)):
        raise Http404

    user_model = get_user_model()
    if is_rescue_admin(request.user):
        recipients = user_model.objects.filter(
            is_active=True,
        ).filter(
            Q(is_superuser=True)
            | Q(
                rescue_assignments__rescue_case=rescue_case,
                rescue_assignments__is_active=True,
            )
        ).exclude(pk=request.user.pk).distinct()
    else:
        recipients = user_model.objects.filter(is_active=True, is_superuser=True)
    recipients = recipients.order_by("full_name", "email")
    form = RescueCaseMessageForm(request.POST if request.method == "POST" else None, recipients=recipients)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            RescueCase.objects.select_for_update().get(pk=pk)
            if not (is_rescue_admin(request.user) or is_case_assignee(request.user, rescue_case)):
                raise Http404
            recipient = form.cleaned_data["recipient"]
            if is_rescue_admin(request.user) and not (
                is_rescue_admin(recipient) or is_case_assignee(recipient, rescue_case)
            ):
                raise Http404
            RescueCaseMessage.objects.create(
                rescue_case=rescue_case,
                sender=request.user,
                recipient=recipient,
                body=form.cleaned_data["body"],
            )
            create_notifications(
                recipient_ids=(recipient.pk,),
                rescue_case=rescue_case,
                kind=Notification.Kind.CASE_MESSAGE,
                title=f"Tin nhắn điều phối riêng cho ca #{pk}",
                message="Bạn có tin nhắn riêng mới về ca cứu hộ.",
                actor=request.user,
                target_url=reverse("rescue:case-messages", args=(pk,)),
            )
        return redirect("rescue:case-messages", pk=pk)

    private_messages = rescue_case.private_messages.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).select_related("sender", "recipient")
    private_messages.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return render(request, "rescue/case_messages.html", {
        "case": rescue_case,
        "private_messages": private_messages,
        "form": form,
        "has_recipients": recipients.exists(),
    })


@require_POST
@login_required
def case_unassign(request, pk, assignment_pk):
    # ===== CHỨC NĂNG CHÍNH: THU HỒI PHÂN CÔNG =====
    # Thu hồi quyền xử lý bằng cách kết thúc phân công, giữ nguyên lịch sử và trao đổi cũ.
    if not is_rescue_admin(request.user):
        return HttpResponseForbidden("Chỉ admin được kết thúc phân công cứu hộ.")
    with transaction.atomic():
        rescue_case = get_object_or_404(RescueCase.objects.select_for_update(), pk=pk)
        assignment = get_object_or_404(
            RescueAssignment.objects.select_for_update(),
            pk=assignment_pk,
            rescue_case=rescue_case,
        )
        if assignment.is_active:
            assignment.is_active = False
            assignment.completed_at = timezone.now()
            assignment.save(update_fields=("is_active", "completed_at"))
            CaseStatusHistory.objects.create(
                rescue_case=rescue_case,
                from_status=rescue_case.status,
                to_status=rescue_case.status,
                changed_by=request.user,
                note="Admin đã kết thúc một phân công xử lý ca cứu hộ.",
            )
            create_notifications(
                recipient_ids=(assignment.assignee_id,),
                rescue_case=rescue_case,
                kind=Notification.Kind.CASE_ASSIGNED,
                title="Phân công cứu hộ của bạn đã kết thúc",
                message=f"Admin đã kết thúc phân công của bạn ở ca #{pk}.",
                actor=request.user,
                target_url=reverse("rescue:notification-list"),
            )
            messages.success(request, "Đã kết thúc phân công và thu hồi quyền xử lý ca của người phụ trách.")
        else:
            messages.info(request, "Phân công này đã kết thúc trước đó.")
    return redirect("rescue:case-detail", pk=pk)
