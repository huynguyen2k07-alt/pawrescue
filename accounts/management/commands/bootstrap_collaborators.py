import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Tạo các tài khoản cộng tác viên hỗ trợ với mật khẩu tạm ngẫu nhiên."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=3,
            help="Số cộng tác viên cần bảo đảm tồn tại (mặc định: 3).",
        )
        parser.add_argument(
            "--domain",
            default="pawrescue.local",
            help="Tên miền email nội bộ dùng cho tài khoản mới.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        if count < 1 or count > 50:
            raise CommandError("--count phải nằm trong khoảng từ 1 đến 50.")

        domain = options["domain"].strip().lower()
        if not domain or "@" in domain or " " in domain:
            raise CommandError("--domain không hợp lệ.")

        user_model = get_user_model()
        created_credentials = []
        existing_count = 0

        with transaction.atomic():
            for index in range(1, count + 1):
                email = f"ctv{index:02d}@{domain}"
                user, created = user_model.objects.get_or_create(
                    email=email,
                    defaults={
                        "full_name": f"Cộng tác viên {index:02d}",
                        "role": user_model.Role.COLLABORATOR,
                        "is_active": True,
                        "is_staff": False,
                    },
                )
                changed_fields = []
                if user.role != user_model.Role.COLLABORATOR:
                    user.role = user_model.Role.COLLABORATOR
                    changed_fields.append("role")
                if not user.is_active:
                    user.is_active = True
                    changed_fields.append("is_active")
                if user.is_staff:
                    user.is_staff = False
                    changed_fields.append("is_staff")

                if created:
                    temporary_password = secrets.token_urlsafe(14)
                    user.set_password(temporary_password)
                    changed_fields.append("password")
                    created_credentials.append((email, temporary_password))
                else:
                    existing_count += 1

                if changed_fields:
                    user.save(update_fields=changed_fields)

        if created_credentials:
            self.stdout.write(self.style.SUCCESS("Tài khoản mới (chỉ hiển thị lần này):"))
            for email, password in created_credentials:
                self.stdout.write(f"  {email}  |  {password}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Hoàn tất: tạo {len(created_credentials)}, đã có {existing_count}."
            )
        )
