
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rescue', '0014_alter_notification_kind'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='kind',
            field=models.CharField(choices=[('case_reported', 'Có tin báo cứu hộ mới'), ('case_claimed', 'Ca đã được tiếp nhận'), ('case_assigned', 'Ca đã được phân công'), ('status_changed', 'Trạng thái đã thay đổi'), ('case_updated', 'Nhật ký cứu hộ mới'), ('case_message', 'Tin nhắn điều phối riêng'), ('adoption_submitted', 'Có đơn nhận nuôi mới'), ('adoption_reviewed', 'Đơn nhận nuôi đã được xét duyệt'), ('adoption_follow_up', 'Nhắc theo dõi sau nhận nuôi'), ('adoption_safety', 'An toàn sau nhận nuôi'), ('support_message', 'Tin nhắn hỗ trợ'), ('donation_submitted', 'Có đóng góp mới'), ('donation_reviewed', 'Đóng góp đã được xác nhận'), ('feedback_received', 'Có góp ý mới')], max_length=30),
        ),
        migrations.CreateModel(
            name='RescueCaseMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField(max_length=2000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='received_case_messages', to=settings.AUTH_USER_MODEL)),
                ('rescue_case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='private_messages', to='rescue.rescuecase')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sent_case_messages', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'tin nhắn điều phối',
                'verbose_name_plural': 'tin nhắn điều phối',
                'ordering': ('created_at', 'pk'),
            },
        ),
    ]
