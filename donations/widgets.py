from django.contrib.admin.widgets import AdminFileWidget


class PrivateAdminFileWidget(AdminFileWidget):
    """Upload widget that doesn't ask private storage for a public URL."""

    template_name = "django/forms/widgets/file.html"

    def is_initial(self, value):
        return bool(value and getattr(value, "name", ""))

    def format_value(self, value):
        return value if self.is_initial(value) else None
