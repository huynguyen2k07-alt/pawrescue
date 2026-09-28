import django.core.validators
import support.models
import support.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("support", "0004_support_permissions_and_assignment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supportattachment",
            name="file",
            field=models.FileField(
                storage=support.storage.PrivateSupportStorage(),
                upload_to="%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=(
                            "jpg",
                            "jpeg",
                            "png",
                            "webp",
                            "mp4",
                            "webm",
                            "mov",
                        )
                    ),
                    support.models.validate_support_attachment_size,
                ],
            ),
        ),
    ]
