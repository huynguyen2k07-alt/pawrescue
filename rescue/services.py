from organizations.models import (
    SYSTEM_ORGANIZATION_NAME,
    OrganizationMembership,
    RescueOrganization,
)


def system_rescue_organization(user=None):
    organization, _created = RescueOrganization.objects.get_or_create(
        is_system=True,
        defaults={
            "name": SYSTEM_ORGANIZATION_NAME,
            "description": "Đội điều phối mặc định của trung tâm PawRescue.",
            "is_verified": True,
            "is_active": True,
            "created_by": None,
        },
    )
    updates = []
    for name, value in {
        "name": SYSTEM_ORGANIZATION_NAME,
        "is_verified": True,
        "is_active": True,
        "created_by_id": None,
    }.items():
        if getattr(organization, name) != value:
            setattr(organization, name, value)
            updates.append("created_by" if name == "created_by_id" else name)
    if updates:
        organization.save(update_fields=updates + ["updated_at"])
    OrganizationMembership.objects.filter(organization=organization).delete()
    return organization
