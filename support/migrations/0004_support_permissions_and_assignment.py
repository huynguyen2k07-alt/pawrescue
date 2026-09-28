from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_role"),
        ("support", "0003_alter_supportattachment_file"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="supportconversation",
            options={
                "ordering": ("-last_message_at",),
                "permissions": (("handle_support", "Có thể xử lý hội thoại hỗ trợ"),),
            },
        ),
        migrations.AlterField(
            model_name="supportconversation",
            name="assigned_to",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to=(
                    models.Q(("is_superuser", True))
                    | models.Q(("role", "collaborator"))
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_support_conversations",
                to="accounts.user",
            ),
        ),
    ]
