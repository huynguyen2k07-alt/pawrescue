from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("member", "Người dùng"),
                    ("collaborator", "Cộng tác viên hỗ trợ"),
                    ("moderator", "Quản trị viên cứu hộ"),
                ],
                default="member",
                max_length=20,
            ),
        ),
    ]
