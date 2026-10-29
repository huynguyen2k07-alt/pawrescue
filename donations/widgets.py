from django.contrib.admin.widgets import AdminFileWidget


class PrivateAdminFileWidget(AdminFileWidget):
    """Ô tải tệp lên sử dụng đường dẫn có kiểm tra quyền cho chứng từ riêng tư."""

    template_name = "donations/widgets/private_admin_file.html"

    def is_initial(self, value):
        return bool(value and getattr(value, "name", ""))

    def format_value(self, value):
        return value if self.is_initial(value) else None
