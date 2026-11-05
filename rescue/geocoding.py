"""Tìm địa chỉ Đà Nẵng qua Geoapify mà không đưa khóa dịch vụ ra trình duyệt."""

import hashlib
import http.client
import json
import math
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.decorators.vary import vary_on_cookie

from .geography import DA_NANG_BOUNDS, is_within_da_nang


_PROVIDER_URL = "https://api.geoapify.com/v1/geocode/search"
_TIMEOUT_SECONDS = 6
_MAX_RESPONSE_BYTES = 128 * 1024
_RESULT_CACHE_SECONDS = 60 * 60
_USER_INTERVAL_SECONDS = 2
_PROVIDER_REQUESTS_PER_SECOND = 5
_CACHE_PREFIX = "rescue:geocoding:v1:"
_UNAVAILABLE_MESSAGE = "Chưa thể tìm địa chỉ lúc này. Vui lòng thử lại sau."
_THROTTLED_MESSAGE = "Bạn đang tìm địa chỉ quá nhanh. Vui lòng chờ một chút rồi thử lại."


class _ProviderUnavailable(Exception):
    pass


class _ProviderThrottled(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _result_cache_key(address, api_key):
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    query_hash = hashlib.sha256(
        f"{key_hash}:{address.casefold()}".encode("utf-8")
    ).hexdigest()
    return f"{_CACHE_PREFIX}result:{query_hash}"


def _remaining_seconds(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _ProviderUnavailable
    return remaining


def _read_body(response, deadline):
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except (TypeError, ValueError):
            raise _ProviderUnavailable from None
        if not 0 <= declared_size <= _MAX_RESPONSE_BYTES:
            raise _ProviderUnavailable

    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type and content_type != "application/json":
        raise _ProviderUnavailable
    if response.headers.get("Content-Encoding", "identity").strip().lower() != "identity":
        raise _ProviderUnavailable

    body = bytearray()
    read = getattr(response, "read1", response.read)
    transport_socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    while True:
        remaining = _remaining_seconds(deadline)
        # Giới hạn cả chuỗi lần đọc; timeout của urllib riêng lẻ không chặn được dữ liệu nhỏ giọt.
        if transport_socket is not None:
            transport_socket.settimeout(remaining)
        chunk = read(min(8192, _MAX_RESPONSE_BYTES + 1 - len(body)))
        _remaining_seconds(deadline)
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise _ProviderUnavailable


def _normalize_results(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise _ProviderUnavailable
    results = []
    seen = set()
    for item in payload["results"]:
        if not isinstance(item, dict):
            continue
        label = item.get("formatted")
        latitude, longitude = item.get("lat"), item.get("lon")
        if not isinstance(label, str) or not label.strip() or len(label) > 500:
            continue
        if type(latitude) not in (int, float) or type(longitude) not in (int, float):
            continue
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (OverflowError, ValueError):
            continue
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            continue
        if not is_within_da_nang(latitude, longitude):
            continue
        country_code = item.get("country_code")
        if country_code is not None and (
            not isinstance(country_code, str) or country_code.lower() != "vn"
        ):
            continue
        label = label.strip()
        identity = (label, latitude, longitude)
        if identity in seen:
            continue
        seen.add(identity)
        results.append({"label": label, "latitude": latitude, "longitude": longitude})
        if len(results) == 5:
            break
    return results


def _search_provider(address, api_key):
    bounds = DA_NANG_BOUNDS
    params = {
        "text": address,
        "lang": "vi",
        "format": "json",
        "limit": 5,
        "filter": (
            f"rect:{bounds['west']},{bounds['south']},{bounds['east']},{bounds['north']}"
            "|countrycode:vn"
        ),
        "apiKey": api_key,
    }
    request = Request(
        f"{_PROVIDER_URL}?{urlencode(params)}",
        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
    )
    deadline = time.monotonic() + _TIMEOUT_SECONDS
    try:
        with build_opener(_NoRedirect()).open(request, timeout=_remaining_seconds(deadline)) as response:
            if response.status == 429:
                raise _ProviderThrottled
            if response.status != 200:
                raise _ProviderUnavailable
            body = _read_body(response, deadline)
        return _normalize_results(json.loads(body))
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if status == 429:
            raise _ProviderThrottled from None
        raise _ProviderUnavailable from None
    except (URLError, OSError, http.client.HTTPException, UnicodeError, ValueError, RecursionError):
        raise _ProviderUnavailable from None


def _error(message, status, retry_after=None):
    response = JsonResponse({"error": message}, status=status)
    if retry_after is not None:
        response["Retry-After"] = str(retry_after)
    return response


@never_cache
@vary_on_cookie
@require_POST
@login_required
def address_search(request):
    # ===== CHỨC NĂNG CHÍNH: TÌM ĐỊA CHỈ QUA MÁY CHỦ =====
    # Chỉ gọi Geoapify khi người dùng bấm tìm; giữ khóa kín và không tạo hồ sơ cứu hộ.
    address = unicodedata.normalize("NFC", " ".join(request.POST.get("address", "").split()))
    if not 5 <= len(address) <= 300:
        return _error("Vui lòng nhập địa chỉ từ 5 đến 300 ký tự.", 400)
    api_key = getattr(settings, "GEOAPIFY_API_KEY", "")
    if not isinstance(api_key, str) or not api_key.strip():
        return _error(_UNAVAILABLE_MESSAGE, 503)
    api_key = api_key.strip()
    cache_key = _result_cache_key(address, api_key)
    try:
        results = cache.get(cache_key)
        if results is not None:
            return JsonResponse({"results": results})
        user_hash = hashlib.sha256(str(request.user.pk).encode("utf-8")).hexdigest()
        if not cache.add(f"{_CACHE_PREFIX}user:{user_hash}", True, timeout=_USER_INTERVAL_SECONDS):
            return _error(_THROTTLED_MESSAGE, 429, _USER_INTERVAL_SECONDS)
        # Các slot hết hạn sau một giây, nên không có đợt gọi dồn ở ranh giới hai giây.
        allowed = any(
            cache.add(f"{_CACHE_PREFIX}provider:{slot}", True, timeout=1)
            for slot in range(_PROVIDER_REQUESTS_PER_SECOND)
        )
        if not allowed:
            return _error(_THROTTLED_MESSAGE, 429, _USER_INTERVAL_SECONDS)
    except Exception:
        return _error(_UNAVAILABLE_MESSAGE, 503)
    try:
        results = _search_provider(address, api_key)
    except _ProviderThrottled:
        return _error("Dịch vụ tìm địa chỉ đang bận. Vui lòng thử lại sau.", 429, 60)
    except _ProviderUnavailable:
        return _error(_UNAVAILABLE_MESSAGE, 503)
    try:
        cache.set(cache_key, results, timeout=_RESULT_CACHE_SECONDS)
    except Exception:
        pass
    return JsonResponse({"results": results})
