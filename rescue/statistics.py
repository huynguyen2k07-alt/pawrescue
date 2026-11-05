"""Tổng hợp số liệu cứu hộ công khai và dựng biểu đồ cho trang chủ."""

import base64
import hashlib
import json
from datetime import datetime, time, timedelta
from io import BytesIO
from threading import Lock

import numpy as np
import pandas as pd
from django.core.cache import cache
from django.db.models import Case, Count, DateField, When
from django.db.models.functions import TruncDate
from django.http import HttpResponseNotModified, JsonResponse
from django.utils import timezone
from django.utils.http import parse_etags, quote_etag
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from .models import RescueCase


_CHART_CACHE_SECONDS = 300
_DAYS_IN_WINDOW = 7
_CHART_SCHEMA_VERSION = 3
_FIGURE_SIZE = (7.2, 3.8)
_CHART_DPI = 130
_CHART_RENDER_LOCK = Lock()
_FOREST = "#26705f"
_ORANGE = "#d66543"
_INK = "#43514d"


def _png_data_url(figure):
    output = BytesIO()
    FigureCanvasAgg(figure).print_png(output)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    figure.clear()
    return f"data:image/png;base64,{encoded}"


def _style_axis(axis):
    axis.set_axisbelow(True)
    axis.grid(axis="y", color="#e7eee9", linewidth=0.8)
    axis.tick_params(colors=_INK, labelsize=10, length=0, pad=8)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.spines["bottom"].set_color("#dde4df")
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_ylabel("Số yêu cầu", fontsize=10, color=_INK, labelpad=10)


def _status_chart(status_rows):
    figure = Figure(figsize=_FIGURE_SIZE, dpi=_CHART_DPI, layout="constrained")
    axis = figure.subplots()
    counts = np.asarray([row["count"] for row in status_rows], dtype=np.int64)
    positions = np.arange(len(status_rows))
    colors = [
        _ORANGE if row["label"] == RescueCase.Status.RESCUED.label else _FOREST
        for row in status_rows
    ]
    bars = axis.barh(positions, counts, height=0.58, color=colors, zorder=3)
    axis.set_yticks(positions, [row["label"] for row in status_rows])
    axis.invert_yaxis()
    axis.set_xlim(0, max(int(np.max(counts)) * 1.2, 1))
    axis.set_axisbelow(True)
    axis.grid(axis="x", color="#e7eee9", linewidth=0.8)
    axis.tick_params(colors=_INK, labelsize=10, length=0, pad=8)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.spines["bottom"].set_color("#dde4df")
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))
    axis.set_xlabel("Số yêu cầu", fontsize=10, color=_INK, labelpad=8)
    axis.bar_label(bars, labels=[str(int(count)) for count in counts], padding=5,
                   color=_INK, fontsize=10)
    return _png_data_url(figure)


def _daily_chart(daily_rows):
    figure = Figure(figsize=_FIGURE_SIZE, dpi=_CHART_DPI, layout="constrained")
    axis = figure.subplots()
    positions = np.arange(len(daily_rows))
    counts = np.asarray([row["count"] for row in daily_rows], dtype=np.int64)
    _style_axis(axis)
    axis.plot(positions, counts, color=_FOREST, linewidth=2.4, marker="o",
              markersize=6, markerfacecolor=_ORANGE, markeredgecolor="white")
    axis.fill_between(positions, counts, color=_FOREST, alpha=0.09)
    axis.set_xticks(positions, [row["date"].strftime("%d/%m") for row in daily_rows])
    axis.set_ylim(0, max(int(np.max(counts)) * 1.3, 1))
    axis.set_xlim(-0.3, len(daily_rows) - 0.7)
    for position, count in zip(positions, counts):
        axis.annotate(str(int(count)), (position, count), xytext=(0, 9),
                      textcoords="offset points", ha="center", color=_INK, fontsize=10)
    return _png_data_url(figure)


def _public_case_counts(first_day, today, site_timezone):
    # ===== CHỨC NĂNG CHÍNH: LẤY SỐ LIỆU CỨU HỘ CÔNG KHAI =====
    # Chỉ đếm trạng thái và ngày nhận request; không đọc nội dung hay thông tin riêng của hồ sơ.
    start = timezone.make_aware(datetime.combine(first_day, time.min), site_timezone)
    end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min), site_timezone)
    public_cases = RescueCase.objects.all().order_by()
    rows = public_cases.annotate(
        day=Case(
            When(reported_at__gte=start, reported_at__lt=end,
                 then=TruncDate("reported_at", tzinfo=site_timezone)),
            output_field=DateField(),
        )
    ).values("status", "day").annotate(count=Count("*"))
    status_counts = {}
    daily_counts = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + row["count"]
        if row["day"] is not None:
            daily_counts[row["day"]] = daily_counts.get(row["day"], 0) + row["count"]
    return status_counts, daily_counts


def _daily_series(daily_counts, first_day, today):
    # ===== CHỨC NĂNG CHÍNH: CHUẨN HÓA SỐ LIỆU THEO NGÀY =====
    # Pandas điền số 0 cho ngày trống, nhờ đó biểu đồ luôn đủ bảy ngày liên tiếp.
    date_index = pd.date_range(first_day, today, freq="D")
    return pd.Series(
        list(daily_counts.values()),
        index=pd.DatetimeIndex(list(daily_counts)),
        dtype="int64",
    ).reindex(date_index, fill_value=0)


def get_public_rescue_statistics():
    # ===== CHỨC NĂNG CHÍNH: VẼ VÀ LƯU ĐỆM BIỂU ĐỒ =====
    # Gộp thành ba nhóm; chỉ vẽ lại khi số liệu hoặc ngày đổi, các lần khác dùng lại ảnh.
    site_timezone = timezone.get_default_timezone()
    today = timezone.localtime(timezone.now(), site_timezone).date()
    first_day = today - timedelta(days=_DAYS_IN_WINDOW - 1)
    status_counts, daily_counts = _public_case_counts(first_day, today, site_timezone)
    rescued_count = int(status_counts.get(RescueCase.Status.RESCUED, 0))
    cancelled_count = sum(
        status_counts.get(status, 0)
        for status in (RescueCase.Status.CANCELLED, RescueCase.Status.CLOSED)
    )
    received_count = sum(status_counts.values()) - rescued_count - cancelled_count
    status_rows = [
        {"label": "Đã xác nhận", "count": int(received_count)},
        {"label": RescueCase.Status.RESCUED.label, "count": rescued_count},
        {"label": RescueCase.Status.CANCELLED.label, "count": int(cancelled_count)},
    ]
    day_series = _daily_series(daily_counts, first_day, today)
    daily_rows = [
        {"date": timestamp.date(), "count": int(count)}
        for timestamp, count in day_series.items()
    ]
    signature = json.dumps({
        "version": _CHART_SCHEMA_VERSION, "timezone": str(site_timezone), "today": today.isoformat(),
        "status": status_rows, "daily": daily_rows,
    }, ensure_ascii=False, sort_keys=True, default=str)
    version = hashlib.sha256(signature.encode()).hexdigest()
    cache_key = "rescue:public-statistics:" + version
    cached = cache.get(cache_key)
    if cached is None:
        with _CHART_RENDER_LOCK:
            cached = cache.get(cache_key)
            if cached is None:
                counts = np.asarray([row["count"] for row in status_rows], dtype=np.int64)
                cached = {
                    "version": version,
                    "time_zone": str(site_timezone),
                    "status_chart": _status_chart(status_rows),
                    "daily_chart": _daily_chart(daily_rows),
                    "status_rows": status_rows,
                    "daily_rows": daily_rows,
                    "total": int(np.sum(counts)),
                    "rescued_count": rescued_count,
                    "daily_average": round(float(np.mean(day_series.to_numpy(dtype=np.int64))), 2),
                    "window_label": f"{first_day:%d/%m/%Y} – {today:%d/%m/%Y}",
                }
                cache.set(cache_key, cached, timeout=_CHART_CACHE_SECONDS)
    return dict(cached, checked_at=timezone.now().isoformat())


@never_cache
@require_GET
def public_statistics_state(request):
    # ===== CHỨC NĂNG CHÍNH: ĐỒNG BỘ BIỂU ĐỒ VỚI TRÌNH DUYỆT =====
    # Mã phiên bản không đổi thì chỉ báo 304, tránh gửi lại hai ảnh sau mỗi năm giây.
    statistics = get_public_rescue_statistics()
    etag = quote_etag(statistics["version"])
    requested_versions = parse_etags(request.headers.get("If-None-Match", ""))
    if any(value == "*" or value.removeprefix("W/") == etag for value in requested_versions):
        response = HttpResponseNotModified()
    else:
        response = JsonResponse(statistics)
    response["ETag"] = etag
    response["X-Statistics-Checked-At"] = statistics["checked_at"]
    return response
