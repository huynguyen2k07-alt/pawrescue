"""Kiểm thử tìm địa chỉ bằng dữ liệu giả, không gọi dịch vụ và không tạo hồ sơ cứu hộ."""

import io
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import path

from .geocoding import (
    _MAX_RESPONSE_BYTES,
    _NoRedirect,
    _ProviderUnavailable,
    _read_body,
    _result_cache_key,
    address_search,
)
from .geography import DA_NANG_BOUNDS


def csrf_token(request):
    return JsonResponse({"token": get_token(request)})


urlpatterns = [
    path("location-search/", address_search),
    path("csrf-token/", csrf_token),
]


class ProviderResponse:
    def __init__(self, body=None, *, status=200, headers=None):
        if body is None:
            body = json.dumps({"results": [{
                "formatted": "12 Đường Kiểm Thử, Đà Nẵng",
                "lat": 16.0544, "lon": 108.2022, "country_code": "vn",
            }]}).encode()
        self.body = io.BytesIO(body)
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.status = status
        self.closed = False
        self.read_sizes = []

    def read(self, size):
        self.read_sizes.append(size)
        return self.body.read(size)

    read1 = read

    def __enter__(self):
        self.body.seek(0)
        self.closed = False
        return self

    def __exit__(self, *args):
        self.closed = True


@override_settings(
    ROOT_URLCONF=__name__, LOGIN_URL="/login/", SECURE_SSL_REDIRECT=False,
    GEOAPIFY_API_KEY="test-only-geoapify-key",
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "geocoding-tests",
    }},
)
class AddressSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = get_user_model().objects.create_user(
            email="geocoding-member@example.com", password="test-password",
        )

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.factory = RequestFactory()
        self.client.force_login(self.member)
        self.provider_response = ProviderResponse()
        self.opener = Mock()
        self.opener.open.return_value = self.provider_response
        self.build_opener = self.enterContext(patch("rescue.geocoding.build_opener", return_value=self.opener))

    def search(self, address="12 Đường Kiểm Thử, Đà Nẵng", *, user=None):
        request = self.factory.post("/location-search/", {"address": address})
        request.user = self.member if user is None else user
        return address_search(request)

    def payload(self, response):
        return json.loads(response.content)

    def fake_results(self, rows):
        self.opener.open.return_value = ProviderResponse(json.dumps({"results": rows}).encode())

    def assert_private(self, response):
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("cookie", response["Vary"].lower())
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def assert_unavailable(self, response):
        self.assertEqual(response.status_code, 503)
        self.assertEqual(set(self.payload(response)), {"error"})
        self.assertNotIn("test-only-geoapify-key", response.content.decode())
        self.assert_private(response)

    def test_requires_login(self):
        response = self.search(user=AnonymousUser())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/login/?next=/location-search/")
        self.assert_private(response)
        self.opener.open.assert_not_called()

    def test_only_accepts_post(self):
        for method in ("get", "put", "delete", "head", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)("/location-search/")
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "POST")
                self.assert_private(response)
        self.opener.open.assert_not_called()

    def test_csrf_is_required_and_valid_token_works(self):
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.member)
        response = secured.post("/location-search/", {"address": "12 Đường Kiểm Thử"})
        self.assertEqual(response.status_code, 403)
        self.opener.open.assert_not_called()
        token = secured.get("/csrf-token/").json()["token"]
        response = secured.post(
            "/location-search/", {"address": "12 Đường Kiểm Thử"}, HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)

    def test_validates_trimmed_address_length_before_calling_provider(self):
        for value in ("", "   ", "  abcd  ", "x" * 301):
            with self.subTest(value=value[:20]):
                response = self.search(value)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(set(self.payload(response)), {"error"})
                self.assert_private(response)
        self.opener.open.assert_not_called()

    def test_missing_field_and_json_body_return_validation_error(self):
        for kwargs in ({}, {"data": json.dumps({"address": "12 Đường Kiểm Thử"}), "content_type": "application/json"}):
            with self.subTest(kwargs=kwargs):
                request = self.factory.post("/location-search/", **kwargs)
                request.user = self.member
                self.assertEqual(address_search(request).status_code, 400)
        self.opener.open.assert_not_called()

    def test_length_boundaries_are_accepted(self):
        for length in (5, 300):
            cache.clear()
            self.assertEqual(self.search("x" * length).status_code, 200)

    def test_provider_url_is_fixed_encoded_filtered_and_never_autocomplete(self):
        query = "https://example.invalid/path?apiKey=attacker & Đà Nẵng"
        response = self.client.post("/location-search/", {
            "address": "  " + query + "  ",
            "url": "http://127.0.0.1/private/", "apiKey": "attacker-key",
            "endpoint": "http://169.254.169.254/", "limit": 100,
        })
        self.assertEqual(response.status_code, 200)
        request = self.opener.open.call_args.args[0]
        parsed = urlsplit(request.full_url)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), (
            "https", "api.geoapify.com", "/v1/geocode/search",
        ))
        bounds = DA_NANG_BOUNDS
        self.assertEqual(parse_qs(parsed.query), {
            "text": [query], "lang": ["vi"], "format": ["json"], "limit": ["5"],
            "apiKey": ["test-only-geoapify-key"],
            "filter": [
                f"rect:{bounds['west']},{bounds['south']},{bounds['east']},{bounds['north']}|countrycode:vn",
            ],
        })
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        timeout = self.opener.open.call_args.kwargs["timeout"]
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 6)
        self.assertIsInstance(self.build_opener.call_args.args[0], _NoRedirect)
        self.assertNotIn("test-only-geoapify-key", response.content.decode())

    def test_query_is_normalized_without_appending_city_keywords(self):
        query = "  12\tĐường   Kiểm Thử, Đà Nẵng\n "
        self.search(query)
        request = self.opener.open.call_args.args[0]
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)["text"], ["12 Đường Kiểm Thử, Đà Nẵng"])

    def test_returns_only_safe_fields_and_five_finite_in_bounds_results(self):
        valid = {"formatted": " Địa chỉ kiểm thử ", "lat": 16.0544, "lon": 108.2022, "country_code": "vn"}
        malformed = [
            None, [], "bad", {},
            {**valid, "lat": True}, {**valid, "lat": "16.0544"},
            {**valid, "lon": False}, {**valid, "lon": None},
            {**valid, "lat": float("nan")}, {**valid, "lon": float("inf")},
            {**valid, "lat": 10.0}, {**valid, "lon": 109.0},
            {**valid, "formatted": "  "}, {**valid, "formatted": []},
            {**valid, "formatted": "x" * 501},
            {**valid, "country_code": "us"}, {**valid, "country_code": 1},
        ]
        rows = malformed + [
            {**valid, "formatted": f"Địa chỉ {index}", "private": "secret", "apiKey": "hidden"}
            for index in range(8)
        ]
        self.fake_results(rows)
        response = self.search()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.payload(response), {"results": [
            {"label": f"Địa chỉ {index}", "latitude": 16.0544, "longitude": 108.2022}
            for index in range(5)
        ]})
        self.assert_private(response)
        self.assertTrue(self.opener.open.return_value.closed)

    def test_accepts_boundary_coordinates_and_removes_duplicates(self):
        self.fake_results([
            {"formatted": "Góc tây nam", "lat": float(DA_NANG_BOUNDS["south"]), "lon": float(DA_NANG_BOUNDS["west"])},
            {"formatted": "Góc đông bắc", "lat": float(DA_NANG_BOUNDS["north"]), "lon": float(DA_NANG_BOUNDS["east"]), "country_code": "VN"},
            {"formatted": " Góc tây nam ", "lat": float(DA_NANG_BOUNDS["south"]), "lon": float(DA_NANG_BOUNDS["west"])},
        ])
        self.assertEqual(len(self.payload(self.search())["results"]), 2)

    def test_no_matching_results_is_success_and_is_cached(self):
        self.fake_results([])
        self.assertEqual(self.payload(self.search()), {"results": []})
        self.assertEqual(self.payload(self.search()), {"results": []})
        self.opener.open.assert_called_once()

    def test_cache_hit_bypasses_provider_and_throttle_for_normalized_query(self):
        first = self.search("12 Đường Kiểm Thử")
        second = self.search("  12   ĐƯỜNG KIỂM THỬ  ")
        self.assertEqual(self.payload(first), self.payload(second))
        self.assertEqual(second.status_code, 200)
        self.opener.open.assert_called_once()

    def test_result_cache_lasts_one_hour_and_key_contains_no_address_or_api_key(self):
        with patch("rescue.geocoding.cache.set", wraps=cache.set) as set_result:
            self.search()
        key, result = set_result.call_args.args
        self.assertEqual(set_result.call_args.kwargs, {"timeout": 3600})
        self.assertEqual(len(key.rsplit(":", 1)[1]), 64)
        self.assertNotIn("Đường", key)
        self.assertNotIn("test-only-geoapify-key", key)
        self.assertEqual(result[0]["latitude"], 16.0544)

    def test_changing_api_key_changes_cache_key_and_does_not_reuse_old_result(self):
        address = "12 Đường Kiểm Thử"
        self.search(address)
        self.assertNotEqual(_result_cache_key(address, "first-key"), _result_cache_key(address, "second-key"))
        with override_settings(GEOAPIFY_API_KEY="different-test-key"):
            response = self.search(address, user=SimpleNamespace(pk=999, is_authenticated=True))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.opener.open.call_count, 2)

    def test_same_user_is_throttled_for_two_seconds_on_cache_miss(self):
        self.assertEqual(self.search("12 Đường Thứ Nhất").status_code, 200)
        response = self.search("34 Đường Thứ Hai")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "2")
        self.assert_private(response)
        self.opener.open.assert_called_once()

    def test_global_slots_allow_at_most_five_provider_requests_across_users(self):
        for index in range(5):
            response = self.search(f"Địa chỉ kiểm thử {index}", user=SimpleNamespace(pk=index + 100, is_authenticated=True))
            self.assertEqual(response.status_code, 200)
        response = self.search("Địa chỉ thứ sáu", user=SimpleNamespace(pk=200, is_authenticated=True))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.opener.open.call_count, 5)

    def test_throttle_slots_use_expiring_add_without_second_bucket(self):
        with patch("rescue.geocoding.cache.add", wraps=cache.add) as add:
            self.search()
        self.assertEqual(add.call_args_list[0].kwargs, {"timeout": 2})
        self.assertTrue(add.call_args_list[0].args[0].startswith("rescue:geocoding:v1:user:"))
        self.assertEqual(add.call_args_list[1].kwargs, {"timeout": 1})
        self.assertEqual(add.call_args_list[1].args[0], "rescue:geocoding:v1:provider:0")

    def test_missing_or_invalid_api_key_never_calls_provider_even_with_cached_result(self):
        self.search()
        self.opener.open.reset_mock()
        for key in ("", "   ", None, 123):
            with self.subTest(key=key), override_settings(GEOAPIFY_API_KEY=key):
                self.assert_unavailable(self.search())
        self.opener.open.assert_not_called()

    def test_transport_errors_timeouts_and_http_errors_are_generic_without_retries(self):
        for error in (
            TimeoutError("sensitive-address test-only-geoapify-key"),
            URLError("sensitive-address test-only-geoapify-key"),
            OSError("sensitive-address test-only-geoapify-key"),
            HTTPError("https://api.geoapify.com/?apiKey=test-only-geoapify-key", 403, "private error", {}, None),
            HTTPError("https://api.geoapify.com/?apiKey=test-only-geoapify-key", 500, "private error", {}, None),
        ):
            with self.subTest(error=type(error).__name__):
                cache.clear()
                self.opener.open.reset_mock()
                self.opener.open.side_effect = error
                response = self.search()
                self.assert_unavailable(response)
                self.assertNotIn("sensitive-address", response.content.decode())
                self.opener.open.assert_called_once()

    def test_provider_429_returns_rate_error_without_native_provider_content(self):
        self.opener.open.side_effect = HTTPError("https://api.geoapify.com/", 429, "secret quota detail", {}, None)
        response = self.search()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")
        self.assertNotIn("secret quota detail", response.content.decode())
        self.opener.open.assert_called_once()
        self.assert_private(response)

    def test_non_200_response_is_not_read_or_cached(self):
        for status in (201, 301, 302, 307, 308, 403, 500):
            with self.subTest(status=status):
                cache.clear()
                provider_response = ProviderResponse(status=status)
                self.opener.open.return_value = provider_response
                self.assert_unavailable(self.search())
                self.assertEqual(provider_response.read_sizes, [])
                self.assertTrue(provider_response.closed)

    def test_redirect_handler_never_builds_follow_up_request(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "http://127.0.0.1/"))

    def test_malformed_json_or_results_returns_unavailable_and_does_not_cache_failure(self):
        for body in (b"not json", b"\xff", b"[]", b"null", b"{}", b'{"results": {}}'):
            with self.subTest(body=body):
                cache.clear()
                self.opener.open.return_value = ProviderResponse(body)
                self.assert_unavailable(self.search())
                self.assertIsNone(cache.get(_result_cache_key("12 Đường Kiểm Thử, Đà Nẵng", "test-only-geoapify-key")))

    def test_deeply_nested_json_returns_generic_unavailable_without_exposing_key(self):
        depth = 10000
        body = b'{"results":' + b"[" * depth + b"]" * depth + b"}"
        self.assertLess(len(body), _MAX_RESPONSE_BYTES)
        self.opener.open.return_value = ProviderResponse(body)
        self.assert_unavailable(self.search())
        self.opener.open.assert_called_once()
        self.assertIsNone(cache.get(_result_cache_key("12 Đường Kiểm Thử, Đà Nẵng", "test-only-geoapify-key")))

    def test_response_size_type_and_encoding_are_bounded(self):
        for body, headers in (
            (b"x" * (_MAX_RESPONSE_BYTES + 1), {}),
            (b"{}", {"Content-Length": str(_MAX_RESPONSE_BYTES + 1)}),
            (b"{}", {"Content-Length": "invalid"}),
            (b"{}", {"Content-Length": "-1"}),
            (b"{}", {"Content-Type": "text/html"}),
            (b"{}", {"Content-Encoding": "gzip"}),
        ):
            with self.subTest(headers=headers, length=len(body)):
                cache.clear()
                provider_response = ProviderResponse(body, headers=headers)
                self.opener.open.return_value = provider_response
                self.assert_unavailable(self.search())
                self.assertTrue(provider_response.closed)
                self.assertLessEqual(provider_response.body.tell(), _MAX_RESPONSE_BYTES + 1)

    def test_exact_body_size_limit_is_accepted(self):
        body = b'{"results": []}'
        body += b" " * (_MAX_RESPONSE_BYTES - len(body))
        self.opener.open.return_value = ProviderResponse(body)
        self.assertEqual(self.payload(self.search()), {"results": []})

    def test_read_deadline_is_rechecked_and_socket_timeout_shrinks(self):
        response = ProviderResponse(b"{}")
        socket = Mock()
        response.fp = SimpleNamespace(raw=SimpleNamespace(_sock=socket))
        with patch("rescue.geocoding.time.monotonic", side_effect=[1, 2, 3, 4]):
            self.assertEqual(_read_body(response, 6), b"{}")
        self.assertEqual([call.args[0] for call in socket.settimeout.call_args_list], [5, 3])

    def test_read_deadline_stops_trickling_response(self):
        response = ProviderResponse(b"{}")
        with patch("rescue.geocoding.time.monotonic", side_effect=[1, 6]):
            with self.assertRaises(_ProviderUnavailable):
                _read_body(response, 6)

    def test_cache_backend_failure_fails_closed_before_provider(self):
        with patch("rescue.geocoding.cache.add", side_effect=OSError("private cache detail")):
            self.assert_unavailable(self.search())
        self.opener.open.assert_not_called()

    def test_cache_write_failure_still_returns_success(self):
        with patch("rescue.geocoding.cache.set", side_effect=OSError("private cache detail")):
            self.assertEqual(self.search().status_code, 200)

    def test_search_has_no_database_or_rescue_side_effects(self):
        models = list(apps.get_app_config("rescue").get_models())
        before = {model: model.objects.count() for model in models}
        with self.assertNumQueries(0):
            response = self.search()
        self.assertEqual(response.status_code, 200)
        self.assertEqual({model: model.objects.count() for model in models}, before)
