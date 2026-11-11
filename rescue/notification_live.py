"""Cung cấp thông báo mới cho chuông chung của website và trang quản trị."""

import hashlib
import json
from urllib.parse import urlsplit, urlunsplit

from django.db.models import Count, Max, Q
from django.http import HttpResponseNotModified, JsonResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_cookie

from accounts.permissions import is_support_operator
from support.context_processors import support_chat

from .notifications import available_notifications


def notification_destination(notification, request):
    """Trả liên kết nội bộ an toàn cho thông báo ở cả HTML và dữ liệu cập nhật."""
    item = notification if isinstance(notification, dict) else {
        "target_url": notification.target_url,
        "rescue_case_id": notification.rescue_case_id,
    }
    target = item["target_url"].strip()
    if (
        target and not target.startswith("//") and "\\" not in target
        and not any(ord(char) < 32 for char in target)
        and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
        )
    ):
        parts = urlsplit(target)
        same_origin = (
            not parts.scheme and not parts.netloc
            or parts.scheme == request.scheme and parts.netloc == request.get_host()
        )
        if same_origin and parts.path.startswith("/") and not parts.path.startswith("//"):
            return urlunsplit(("", "", parts.path, parts.query, parts.fragment))
    if item["rescue_case_id"]:
        return reverse("rescue:case-detail", args=(item["rescue_case_id"],))
    return reverse("rescue:notification-list")


def _serialize_items(queryset, request):
    fields = ("pk", "kind", "display_title", "is_read", "created_at", "target_url", "rescue_case_id")
    return [
        {
            "id": item["pk"],
            "kind": item["kind"],
            "title": item["display_title"],
            "is_read": item["is_read"],
            "created_at": item["created_at"].isoformat(),
            "url": notification_destination(item, request),
            "open_url": reverse("rescue:notification-open", args=(item["pk"],)),
        }
        for item in queryset.order_by("-created_at", "-pk").values(*fields)[:20]
    ]


def notification_snapshot(request):
    user = request.user
    notifications = available_notifications(user)
    counts = notifications.aggregate(
        total_count=Count("pk"),
        unread_count=Count("pk", filter=Q(is_read=False)),
        latest_id=Max("pk"),
    )
    payload = {
        "user_id": user.pk,
        "unread_count": counts["unread_count"],
        "total_count": counts["total_count"],
        "latest_id": counts["latest_id"] or 0,
        "support_unread_count": (
            support_chat(request)["support_admin_unread_count"]
            if is_support_operator(user) else 0
        ),
        "items": _serialize_items(notifications, request),
        "unread_items": _serialize_items(notifications.filter(is_read=False), request),
    }
    version = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return {**payload, "version": version}


# ===== CHỨC NĂNG CHÍNH: CẬP NHẬT THÔNG BÁO TRÊN MỌI TRANG =====
# Dùng chung số đếm theo quyền cho kiểm tra định kỳ và phản hồi sau khi người dùng đánh dấu đã đọc.
@never_cache
@vary_on_cookie
def notification_state(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse({"error": "Hãy đăng nhập để nhận thông báo."}, status=401)
    if request.method != "GET":
        response = JsonResponse({"error": "Chức năng này chỉ nhận yêu cầu GET."}, status=405)
        response["Allow"] = "GET"
        return response
    payload = notification_snapshot(request)
    etag = f'"{payload["version"]}"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
    else:
        response = JsonResponse(payload)
    response["ETag"] = etag
    return response
