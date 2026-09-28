from django.contrib.admin.widgets import AdminFileWidget


class PrivateAdminImageWidget(AdminFileWidget):
    # The regular admin widget dereferences ``value.url`` for existing files.
    # Private storage intentionally has no URL, so render only the file input.
    template_name = "django/forms/widgets/file.html"

    def is_initial(self, value):
        return bool(value and getattr(value, "name", ""))

    def format_value(self, value):
        return value if self.is_initial(value) else None
