from .models import OrganizationMembership, RescueOrganization


MANAGER_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.MANAGER,
)


def can_manage_organization(user, organization):
    if user is None or not user.is_authenticated:
        return False
    if getattr(user, "is_moderator", False) and not user.is_superuser:
        return False
    if user.is_superuser:
        return True
    if (
        not organization.is_active
        or not organization.is_verified
        or organization.is_system
    ):
        return False
    return organization.memberships.filter(
        user=user,
        is_active=True,
        role__in=MANAGER_ROLES,
    ).exists()


def fundraising_organizations(user):
    if user is None or not user.is_authenticated:
        return RescueOrganization.objects.none()
    if getattr(user, "is_moderator", False) and not user.is_superuser:
        return RescueOrganization.objects.none()
    organizations = RescueOrganization.objects.filter(is_active=True)
    if user.is_superuser:
        return organizations
    return organizations.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__role__in=MANAGER_ROLES,
        is_verified=True,
    ).distinct()


def managed_organizations(user):
    """Lấy tổ chức đang hoạt động mà người dùng được phép quản lý; dùng chung với mã nhận nuôi cũ."""
    organizations = fundraising_organizations(user).filter(is_verified=True)
    if user is None or not user.is_superuser:
        organizations = organizations.filter(is_system=False)
    return organizations
