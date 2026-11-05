"""Kiểm tra giao diện cứu hộ gọn vẫn giữ thao tác thật và giới hạn theo vai trò."""

from collections import Counter
from decimal import Decimal
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from organizations.models import RescueOrganization

from .models import RescueCase


class _CaseMarkup(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.ids = []
        self.forms = []
        self.details = {}
        self.inputs = []
        self.links = {}
        self.scripts = []
        self.buttons = {}
        self.feed(content)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag == "form":
            self.forms.append(attrs)
        elif tag == "details" and attrs.get("id"):
            self.details[attrs["id"]] = attrs
        elif tag == "input":
            self.inputs.append(attrs)
        elif tag == "a" and attrs.get("id"):
            self.links[attrs["id"]] = attrs
        elif tag == "script" and attrs.get("src"):
            self.scripts.append(attrs)
        elif tag == "button" and attrs.get("id"):
            self.buttons[attrs["id"]] = attrs


class SimpleCaseTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser(
            email="simple-workspace-admin@example.com", password="test-password",
        )
        cls.reporter = users.objects.create_user(
            email="simple-workspace-reporter@example.com", password="test-password",
        )
        cls.case = RescueCase.objects.create(
            title="Tin cứu hộ cần xác minh", description="Con vật đang bị thương.",
            animal_type=RescueCase.AnimalType.CAT,
            address="430 Hùng Vương, Hải Châu, Đà Nẵng",
            latitude="16.054407", longitude="108.202167",
            reporter=cls.reporter, is_location_private=True,
        )
        RescueOrganization.objects.create(
            name="Đội cứu hộ ngoài hệ thống", created_by=cls.admin,
            is_verified=True, phone="0901234567", email="rescue-team@example.com",
        )

    def test_admin_workspace_keeps_real_actions_and_collapses_long_forms(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("rescue:case-detail", args=(self.case.pk,)))
        self.assertEqual(response.status_code, 200)
        markup = _CaseMarkup(response.content.decode())
        actions = {form.get("action"): form.get("method") for form in markup.forms}
        for name in ("case-claim", "case-handoff", "case-update-status", "case-assign", "case-notify-admins"):
            self.assertEqual(actions[reverse(f"rescue:{name}", args=(self.case.pk,))], "post")
        self.assertEqual(actions[reverse("support:open-case-chat", args=(self.case.pk,))], "post")
        self.assertContains(response, 'id="case-complete"')
        self.assertContains(response, "Xử lý thành công")
        self.assertContains(response, "Gửi ca cho các quản trị viên")
        for element_id in ("case-review", "case-handoff", "case-assign", "case-history"):
            self.assertNotIn("open", markup.details[element_id])
        self.assertContains(response, reverse("admin:rescue_rescuecase_change", args=(self.case.pk,)) + "?edit=1")
        self.assertContains(response, reverse("admin:rescue_rescuecase_delete", args=(self.case.pk,)))
        self.assertNotContains(response, "onclick=")
        self.assertFalse([value for value, count in Counter(markup.ids).items() if count > 1])

    def test_reporter_keeps_status_and_community_navigation_without_admin_tools(self):
        self.client.force_login(self.reporter)
        response = self.client.get(reverse("rescue:case-detail", args=(self.case.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Theo dõi tin báo")
        self.assertContains(response, self.case.address)
        self.assertNotContains(response, 'id="case-review"')
        self.assertNotContains(response, 'id="case-handoff"')
        self.assertNotContains(response, 'id="case-complete"')
        self.assertNotContains(response, "Gửi ca cho các quản trị viên")
        self.assertNotContains(response, reverse("admin:rescue_rescuecase_delete", args=(self.case.pk,)))
        self.assertContains(response, f'href="{reverse("rescue:knowledge-list")}"')
        self.assertContains(response, f'href="{reverse("rescue:team")}"')

    def test_success_confirmation_keeps_private_address_hidden_from_public(self):
        self.case.status = RescueCase.Status.RESCUED
        self.case.save(update_fields=("status",))
        url = reverse("rescue:case-detail", args=(self.case.pk,))

        response = self.client.get(url)
        self.assertContains(response, "Xem trên bản đồ cứu hộ thành công")
        self.assertNotContains(response, self.case.address)
        self.assertNotContains(response, 'id="case-complete"')

        self.client.force_login(self.reporter)
        response = self.client.get(url)
        self.assertContains(response, "Địa chỉ đã xử lý:")
        self.assertContains(response, self.case.address)

    def test_report_form_has_one_coordinate_pair_and_opens_manual_entry_on_error(self):
        self.client.force_login(self.reporter)
        url = reverse("rescue:case-create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        markup = _CaseMarkup(response.content.decode())
        for name in ("latitude", "longitude"):
            self.assertEqual(sum(item.get("name") == name for item in markup.inputs), 1)
        self.assertNotIn("open", markup.details["manual-coordinates"])
        self.assertFalse([value for value, count in Counter(markup.ids).items() if count > 1])

        invalid = self.client.post(url, {
            "title": "Thiếu vị trí", "animal_type": "cat", "urgency": "high",
            "description": "Cần cứu hộ", "address": "Hải Châu, Đà Nẵng",
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertIn("open", _CaseMarkup(invalid.content.decode()).details["manual-coordinates"])

    def test_report_has_one_location_picker_without_the_google_maps_paste_step(self):
        self.client.force_login(self.reporter)
        response = self.client.get(reverse("rescue:case-create"))
        markup = _CaseMarkup(response.content.decode())
        self.assertEqual(markup.ids.count("use-current-location"), 1)
        self.assertEqual(markup.ids.count("location-picker-map"), 1)
        self.assertEqual(markup.buttons["use-current-location"]["type"], "button")
        for removed in ("open-location-map", "location-coordinate-source", "apply-map-location", "location-alternative.js"):
            self.assertNotContains(response, removed)
        sources = [script["src"] for script in markup.scripts]
        leaflet = next(i for i, src in enumerate(sources) if "/vendor/leaflet/leaflet.js" in src)
        maps = next(i for i, src in enumerate(sources) if "/js/maps.js" in src)
        self.assertLess(leaflet, maps)
        self.assertIn("defer", markup.scripts[leaflet])
        self.assertIn("defer", markup.scripts[maps])
        self.assertContains(response, "/static/vendor/leaflet/leaflet.css")
        self.assertNotContains(response, "unpkg.com/leaflet")

    def test_selected_coordinate_fields_save_the_report(self):
        self.client.force_login(self.reporter)
        response = self.client.post(reverse("rescue:case-create"), {
            "title": "[QA-PIN] Báo tin đã chọn ghim",
            "animal_type": "cat", "urgency": "high",
            "description": "Con vật đang bị thương, cần kiểm tra.",
            "address": "Cổng chợ Hàn, phía đường Trần Phú, Đà Nẵng",
            "latitude": "16.054407", "longitude": "108.202167",
            "location_confirmed": "on",
            "contact_phone": "0901234567", "is_location_private": "on",
        })
        self.assertEqual(response.status_code, 302)
        case = RescueCase.objects.get(title="[QA-PIN] Báo tin đã chọn ghim")
        self.assertEqual(case.reporter, self.reporter)
        self.assertEqual(case.latitude, Decimal("16.054407"))
        self.assertEqual(case.longitude, Decimal("108.202167"))
        self.assertEqual(case.address, "Cổng chợ Hàn, phía đường Trần Phú, Đà Nẵng")
        self.assertEqual(case.status, RescueCase.Status.REPORTED)
        self.assertTrue(case.is_location_private)

    @override_settings(GEOAPIFY_API_KEY="fake-template-key")
    def test_address_search_uses_private_endpoint_without_rendering_the_provider_key(self):
        self.client.force_login(self.reporter)
        response = self.client.get(reverse("rescue:case-create"))
        markup = _CaseMarkup(response.content.decode())
        self.assertContains(response, "data-address-search")
        self.assertContains(response, reverse("rescue:location-search"))
        self.assertContains(response, "https://www.geoapify.com/")
        self.assertNotContains(response, "fake-template-key")
        self.assertEqual(markup.ids.count("find-address"), 1)
        self.assertEqual(markup.buttons["find-address"]["type"], "button")
        self.assertEqual(markup.ids.count("id_location_confirmed"), 1)
        sources = [script["src"] for script in markup.scripts]
        maps = next(i for i, src in enumerate(sources) if "/js/maps.js" in src)
        search = next(i for i, src in enumerate(sources) if "/js/address-search.js" in src)
        self.assertLess(maps, search)
        self.assertIn("defer", markup.scripts[search])

    @override_settings(GEOAPIFY_API_KEY="")
    def test_missing_provider_key_keeps_the_existing_picker_without_a_broken_search(self):
        self.client.force_login(self.reporter)
        response = self.client.get(reverse("rescue:case-create"))
        self.assertNotContains(response, "data-address-search")
        self.assertNotContains(response, "/js/address-search.js")
        self.assertContains(response, 'id="use-current-location"')
