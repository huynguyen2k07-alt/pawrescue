from importlib import import_module
from io import StringIO
from types import SimpleNamespace

from django.apps import apps
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from .management.commands.seed_pawrescue_content import ARTICLES
from .models import KnowledgeArticle


@override_settings(SECURE_SSL_REDIRECT=False)
class RetiredAdoptionContentTests(TestCase):
    slug = "30-ngay-dau-sau-khi-nhan-nuoi"
    title = "30 ngày đầu sau khi nhận nuôi: giúp pet làm quen nhà mới"

    def test_seed_retains_archived_article_without_republishing_or_overwriting_edits(self):
        article = KnowledgeArticle.objects.create(
            title=self.title,
            slug=self.slug,
            category=KnowledgeArticle.Category.CARE,
            excerpt="Nội dung đã được quản trị viên chỉnh sửa.",
            body="Giữ nguyên phần ghi chú này trong hồ sơ lưu trữ.",
            is_published=True,
            is_featured=True,
        )
        call_command("seed_pawrescue_content", stdout=StringIO())
        call_command("seed_pawrescue_content", stdout=StringIO())
        article.refresh_from_db()

        self.assertFalse(article.is_published)
        self.assertFalse(article.is_featured)
        self.assertEqual(article.excerpt, "Nội dung đã được quản trị viên chỉnh sửa.")
        self.assertEqual(article.body, "Giữ nguyên phần ghi chú này trong hồ sơ lưu trữ.")
        self.assertEqual(KnowledgeArticle.objects.count(), len(ARTICLES))
        for url in (reverse("rescue:case-list"), reverse("rescue:knowledge-list")):
            self.assertNotContains(self.client.get(url), self.title)
        self.assertEqual(self.client.get(article.get_absolute_url()).status_code, 404)

    def test_archive_migration_only_unpublishes_known_seed_identity(self):
        seed = KnowledgeArticle.objects.create(
            title=self.title,
            slug=self.slug,
            category=KnowledgeArticle.Category.CARE,
            excerpt="Nội dung cũ.",
            body="Nội dung đã chỉnh sửa cần được giữ lại.",
            is_published=True,
            is_featured=True,
        )
        custom_article = KnowledgeArticle.objects.create(
            title="Ghi chép chăm sóc của quản trị viên",
            slug="ghi-chep-cham-soc-rieng",
            category=KnowledgeArticle.Category.CARE,
            excerpt="Ghi chép riêng.",
            body="Nội dung của người dùng.",
            is_published=True,
            is_featured=True,
        )
        migration = import_module("rescue.migrations.0016_archive_seeded_adoption_article")
        migration.archive_seeded_adoption_article(
            apps, SimpleNamespace(connection=connection)
        )
        seed.refresh_from_db()
        custom_article.refresh_from_db()

        self.assertFalse(seed.is_published)
        self.assertFalse(seed.is_featured)
        self.assertEqual(seed.body, "Nội dung đã chỉnh sửa cần được giữ lại.")
        self.assertTrue(custom_article.is_published)
        self.assertTrue(custom_article.is_featured)
