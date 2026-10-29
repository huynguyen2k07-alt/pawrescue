"""Kiểm thử tọa độ trong thuộc tính HTML vẫn được JavaScript đọc đúng khi giao diện dùng tiếng Việt."""

from decimal import Decimal
from html.parser import HTMLParser

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils.translation import override

from .forms import RescueCaseForm


class MapAttributes(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.picker = None
        self.inputs = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-map-picker" in attrs:
            self.picker = attrs
        if tag == "input" and attrs.get("id") in ("id_latitude", "id_longitude"):
            self.inputs[attrs["id"]] = attrs


class MapCoordinateTemplateTests(SimpleTestCase):
    latitude = "16.054407"
    longitude = "108.202167"

    def assert_picker_coordinates(self, form):
        with override("vi"):
            html = render_to_string("rescue/case_form.html", {
                "form": form, "user": AnonymousUser(), "csrf_token": "test-token",
            })
        attrs = MapAttributes(html)
        self.assertIsNotNone(attrs.picker)
        self.assertEqual(attrs.picker["data-latitude"], self.latitude)
        self.assertEqual(attrs.picker["data-longitude"], self.longitude)
        self.assertEqual(attrs.inputs["id_latitude"]["value"], self.latitude)
        self.assertEqual(attrs.inputs["id_longitude"]["value"], self.longitude)

    def test_initialized_decimal_coordinates_use_dot_separator_in_vietnamese(self):
        self.assert_picker_coordinates(RescueCaseForm(initial={
            "latitude": Decimal(self.latitude), "longitude": Decimal(self.longitude),
        }))

    def test_invalid_report_redisplays_exact_coordinates_for_map_picker(self):
        form = RescueCaseForm(data={
            "title": "", "description": "A cat needs help.",
            "animal_type": "cat", "urgency": "high",
            "address": "430 Hùng Vương, Hải Châu, Đà Nẵng",
            "latitude": self.latitude, "longitude": self.longitude,
        })
        with override("vi"):
            self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)
        self.assertNotIn("latitude", form.errors)
        self.assertNotIn("longitude", form.errors)
        self.assert_picker_coordinates(form)
