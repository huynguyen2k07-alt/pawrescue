from django.db import migrations, models


STATUS_CHOICES = [
    ("reported", "Đã báo tin"),
    ("verified", "Đã xác nhận"),
    ("assigned", "Đã phân công"),
    ("in_progress", "Đang cứu hộ"),
    ("rescued", "Đã cứu thành công"),
    ("closed", "Đã đóng"),
    ("cancelled", "Đã hủy"),
]


class Migration(migrations.Migration):
    dependencies = [("rescue", "0010_contributorprofile_knowledgearticle_and_more")]

    operations = [
        migrations.AlterField(
            model_name="casestatushistory",
            name="from_status",
            field=models.CharField(
                blank=True,
                choices=STATUS_CHOICES,
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="casestatushistory",
            name="to_status",
            field=models.CharField(choices=STATUS_CHOICES, max_length=20),
        ),
        migrations.AlterField(
            model_name="rescuecase",
            name="status",
            field=models.CharField(
                choices=STATUS_CHOICES,
                default="reported",
                max_length=20,
            ),
        ),
    ]
