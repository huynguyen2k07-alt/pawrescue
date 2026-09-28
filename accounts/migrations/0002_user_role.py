from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("member", "Người dùng"),
                    ("collaborator", "Cộng tác viên hỗ trợ"),
                ],
                default="member",
                max_length=20,
            ),
        ),
    ]
