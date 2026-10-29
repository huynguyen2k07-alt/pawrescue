
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0005_remove_gif_support'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='supportconversation',
            name='assigned_to',
            field=models.ForeignKey(blank=True, limit_choices_to=models.Q(('is_active', True), models.Q(('is_superuser', True), ('role', 'collaborator'), models.Q(('user_permissions__codename', 'handle_support'), ('user_permissions__content_type__app_label', 'support')), models.Q(('groups__permissions__codename', 'handle_support'), ('groups__permissions__content_type__app_label', 'support')), _connector='OR')), null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_support_conversations', to=settings.AUTH_USER_MODEL),
        ),
    ]
