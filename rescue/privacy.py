"""Giới hạn dữ liệu hồ sơ cứu hộ theo người báo tin và đội được phân công."""

from types import SimpleNamespace

from django.db.models import Case, CharField, Q, Value, When
from django.db.models.functions import Cast, Concat
from django.urls import reverse

from .models import RescueAssignment, RescueCase
from .permissions import is_rescue_admin


def _active_user(user):
    return bool(user and user.is_authenticated and user.is_active and user.pk is not None)


def _active_assignee(user, rescue_case):
    prefetched = getattr(rescue_case, "_prefetched_objects_cache", {}).get("assignments")
    if prefetched is not None:
        return any(item.assignee_id == user.pk and item.is_active for item in prefetched)
    return rescue_case.assignments.filter(assignee_id=user.pk, is_active=True).exists()


def can_view_case_details(user, rescue_case):
    """Hồ sơ gốc chỉ dành cho admin, người báo tin và người đang được giao ca."""
    return _active_user(user) and (
        is_rescue_admin(user) or rescue_case.reporter_id == user.pk
        or _active_assignee(user, rescue_case)
    )


def can_view_case_internal(user, rescue_case):
    """Chỉ admin và người đang được giao ca xem phần điều phối nội bộ."""
    return _active_user(user) and (
        is_rescue_admin(user) or _active_assignee(user, rescue_case)
    )


def present_case(user, rescue_case):
    # ===== CHỨC NĂNG CHÍNH: BẢO VỆ HỒ SƠ CỨU HỘ KHI CÔNG KHAI =====
    # Tạo bản xem an toàn thay vì đưa model gốc ra trang của người không liên quan.
    if can_view_case_details(user, rescue_case):
        return rescue_case

    animal_label = dict(RescueCase.AnimalType.choices).get(rescue_case.animal_type, "Động vật")
    status_label = dict(RescueCase.Status.choices).get(rescue_case.status, "Đang cập nhật")
    urgency_label = dict(RescueCase.Urgency.choices).get(rescue_case.urgency, "Đang cập nhật")
    organization = rescue_case.organization
    public_organization = None
    if organization is not None:
        public_organization = SimpleNamespace(
            pk=organization.pk, id=organization.pk, name=organization.name,
            is_system=organization.is_system, phone="", email="", address="", website="",
        )
    case_id = rescue_case.pk
    return SimpleNamespace(
        pk=case_id,
        id=case_id,
        title=f"Ca cứu hộ {animal_label} #{case_id}",
        description=f"Trạng thái: {status_label}. Hồ sơ hiện trường và thông tin liên hệ được bảo vệ.",
        animal_type=rescue_case.animal_type,
        animal_details="",
        status=rescue_case.status,
        urgency=rescue_case.urgency,
        address="Khu vực gần đúng tại Đà Nẵng",
        latitude=None,
        longitude=None,
        is_location_private=True,
        reporter=None,
        reporter_id=None,
        contact_name="",
        contact_phone="",
        organization=public_organization,
        organization_id=organization.pk if organization is not None else None,
        reported_at=rescue_case.reported_at,
        updated_at=rescue_case.updated_at,
        closed_at=rescue_case.closed_at,
        images=SimpleNamespace(all=lambda: ()),
        get_animal_type_display=lambda: animal_label,
        get_status_display=lambda: status_label,
        get_urgency_display=lambda: urgency_label,
        get_absolute_url=lambda: reverse("rescue:case-detail", args=(case_id,)),
    )


def _choice_label_expression(field_name, choices, default):
    return Case(
        *(When(**{field_name: value}, then=Value(label.casefold())) for value, label in choices),
        default=Value(default.casefold()),
        output_field=CharField(),
    )


def filter_case_search(queryset, user, query):
    """Không để kết quả tìm kiếm tiết lộ địa chỉ hay nội dung hồ sơ bị ẩn."""
    query = query.strip()
    if not query:
        return queryset

    public_query = query.casefold()
    animal_label = _choice_label_expression("animal_type", RescueCase.AnimalType.choices, "Động vật")
    queryset = queryset.alias(
        _public_case_title=Concat(
            Value("ca cứu hộ "), animal_label, Value(" #"), Cast("pk", CharField()),
            output_field=CharField(),
        ),
        _public_case_animal=animal_label,
        _public_case_status=_choice_label_expression("status", RescueCase.Status.choices, "Đang cập nhật"),
    )
    public_match = (
        Q(_public_case_title__icontains=public_query)
        | Q(_public_case_animal__icontains=public_query)
        | Q(_public_case_status__icontains=public_query)
    )
    numeric_query = query.removeprefix("#")
    if numeric_query.isascii() and numeric_query.isdigit() and len(numeric_query) <= 19:
        case_id = int(numeric_query)
        if case_id <= 9223372036854775807:
            public_match |= Q(pk=case_id)

    raw_match = Q(title__icontains=query) | Q(description__icontains=query) | Q(address__icontains=query)
    if is_rescue_admin(user):
        return queryset.filter(public_match | raw_match)
    if _active_user(user):
        assigned_case_ids = RescueAssignment.objects.filter(
            assignee_id=user.pk, is_active=True,
        ).values("rescue_case_id")
        details_allowed = Q(reporter_id=user.pk) | Q(pk__in=assigned_case_ids)
        return queryset.filter(public_match | (details_allowed & raw_match))
    return queryset.filter(public_match)
