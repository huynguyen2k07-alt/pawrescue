from django.db import migrations


def archive_seeded_adoption_article(apps, schema_editor):
    KnowledgeArticle = apps.get_model("rescue", "KnowledgeArticle")
    KnowledgeArticle.objects.using(schema_editor.connection.alias).filter(
        slug="30-ngay-dau-sau-khi-nhan-nuoi",
        title="30 ngày đầu sau khi nhận nuôi: giúp pet làm quen nhà mới",
    ).update(is_published=False, is_featured=False)


class Migration(migrations.Migration):
    dependencies = [
        ("rescue", "0015_alter_notification_kind_rescuecasemessage"),
    ]

    operations = [
        migrations.RunPython(archive_seeded_adoption_article, migrations.RunPython.noop),
    ]
