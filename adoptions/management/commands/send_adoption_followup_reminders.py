from django.core.management.base import BaseCommand

from adoptions.reminders import dispatch_due_follow_up_reminders


class Command(BaseCommand):
    help = "Gửi các thông báo theo dõi nhận nuôi đến hạn ở tháng 1, 2 và 3."

    def handle(self, *args, **options):
        sent_count = dispatch_due_follow_up_reminders()
        self.stdout.write(
            self.style.SUCCESS(f"Đã gửi {sent_count} thông báo theo dõi nhận nuôi.")
        )
