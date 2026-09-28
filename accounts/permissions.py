from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import Q


SUPPORT_PERMISSION = "support.handle_support"


def is_support_operator(user):
    """Return whether a user may work in the support/collaborator portal."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return bool(
        user.is_superuser
        or getattr(user, "is_collaborator", False)
        or user.has_perm(SUPPORT_PERMISSION)
    )


def support_operator_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_support_operator(request.user):
            raise PermissionDenied("Bạn không có quyền truy cập khu vực cộng tác viên.")
        return view_func(request, *args, **kwargs)

    return wrapped


def support_operator_queryset(user_model):
    """Active operators, including users granted the explicit permission."""
    return user_model.objects.filter(is_active=True).filter(
        Q(is_superuser=True)
        | Q(role=user_model.Role.COLLABORATOR)
        | Q(
            user_permissions__content_type__app_label="support",
            user_permissions__codename="handle_support",
        )
        | Q(
            groups__permissions__content_type__app_label="support",
            groups__permissions__codename="handle_support",
        )
    ).distinct()


def support_operator_ids(user_model):
    return support_operator_queryset(user_model).values_list("pk", flat=True)
