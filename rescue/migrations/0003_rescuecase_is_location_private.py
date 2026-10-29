
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rescue', '0002_alter_casestatushistory_from_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='rescuecase',
            name='is_location_private',
            field=models.BooleanField(default=False, help_text='Chỉ người báo tin và đội cứu hộ thấy vị trí chính xác.'),
        ),
    ]
