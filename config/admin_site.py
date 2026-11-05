from django.contrib.admin.apps import AdminConfig
from django.contrib.admin.sites import AdminSite
from django.urls import reverse


class RescueAdminSite(AdminSite):
    visible_models = {
        "rescue.rescuecase": "Yêu cầu cứu hộ",
        "accounts.user": "Tài khoản và nhân sự",
        "organizations.rescueorganization": "Đơn vị tiếp nhận",
    }
    app_labels = {
        "rescue": "Cứu hộ",
        "accounts": "Nhân sự",
        "organizations": "Đơn vị tiếp nhận",
    }
    app_order = ("rescue", "accounts", "organizations")

    def has_permission(self, request):
        if getattr(request.user, "is_moderator", False) and not request.user.is_superuser:
            return False
        return super().has_permission(request)

    def get_app_list(self, request, app_label=None):
        # Chỉ thu gọn các mục hiển thị; quyền và đường dẫn quản trị dữ liệu vẫn được giữ nguyên.
        app_list = super().get_app_list(request, app_label)
        visible_apps = []
        for app in app_list:
            models = []
            for model_info in app["models"]:
                key = model_info["model"]._meta.label_lower
                if key in self.visible_models:
                    model_info["name"] = self.visible_models[key]
                    models.append(model_info)
            if models:
                app["models"] = models
                app["name"] = self.app_labels[app["app_label"]]
                visible_apps.append(app)
        return sorted(
            visible_apps,
            key=lambda app: self.app_order.index(app["app_label"]),
        )

    def each_context(self, request):
        from accounts.permissions import is_support_operator

        context = super().each_context(request)
        models = {
            item["model"]._meta.label_lower: item
            for app in context["available_apps"]
            for item in app["models"]
        }
        navigation = []
        for key, model_key, label, description in (
            ("cases", "rescue.rescuecase", "Yêu cầu cứu hộ", "Tiếp nhận và xử lý tin báo"),
            ("inbox", None, "Hộp thư", "Trao đổi với người báo tin"),
            ("personnel", "accounts.user", "Tài khoản và nhân sự", "Người báo tin và người phụ trách"),
            ("organizations", "organizations.rescueorganization", "Đơn vị tiếp nhận", "Danh bạ các tổ chức phối hợp"),
        ):
            if key == "inbox":
                if not self.has_permission(request) or not is_support_operator(request.user):
                    continue
                url = reverse("support:inbox")
            else:
                info = models.get(model_key)
                if not info or not info.get("admin_url"):
                    continue
                url = info["admin_url"]
            navigation.append({
                "key": key,
                "label": label,
                "description": description,
                "url": url,
                "active": request.path.startswith(url),
            })
        context["operational_nav"] = navigation
        return context


class RescueAdminConfig(AdminConfig):
    default_site = "config.admin_site.RescueAdminSite"
