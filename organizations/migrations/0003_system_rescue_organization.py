from django.db import migrations, models


SYSTEM_ORGANIZATION_NAME = "PawRescue"


def reserve_system_organization(apps, schema_editor):
    RescueOrganization = apps.get_model(
        "organizations",
        "RescueOrganization",
    )
    OrganizationMembership = apps.get_model(
        "organizations",
        "OrganizationMembership",
    )

    candidates = list(
        RescueOrganization.objects.filter(
            name__iexact=SYSTEM_ORGANIZATION_NAME
        ).order_by("pk")
    )
    if candidates:
        system_organization = candidates[0]
        for duplicate in candidates[1:]:
            duplicate.name = f"PawRescue legacy {duplicate.pk}"
            duplicate.is_system = False
            duplicate.save(update_fields=("name", "is_system"))
    else:
        system_organization = RescueOrganization.objects.create(
            name=SYSTEM_ORGANIZATION_NAME,
            description="Đội điều phối mặc định của trung tâm PawRescue.",
            is_verified=True,
            is_active=True,
            is_system=True,
        )

    system_organization.name = SYSTEM_ORGANIZATION_NAME
    system_organization.is_verified = True
    system_organization.is_active = True
    system_organization.is_system = True
    system_organization.created_by_id = None
    system_organization.save(
        update_fields=(
            "name",
            "is_verified",
            "is_active",
            "is_system",
            "created_by",
        )
    )
    OrganizationMembership.objects.filter(
        organization_id=system_organization.pk
    ).delete()


def unreserve_system_organization(apps, schema_editor):
    RescueOrganization = apps.get_model(
        "organizations",
        "RescueOrganization",
    )
    RescueOrganization.objects.filter(is_system=True).update(is_system=False)


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0002_alter_organizationmembership_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="rescueorganization",
            name="is_system",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.RunPython(
            reserve_system_organization,
            unreserve_system_organization,
        ),
        migrations.AddConstraint(
            model_name="rescueorganization",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_system", True)),
                fields=("is_system",),
                name="single_system_rescue_organization",
            ),
        ),
        migrations.AddConstraint(
            model_name="rescueorganization",
            constraint=models.CheckConstraint(
                condition=models.Q(("is_system", False))
                | models.Q(("name", SYSTEM_ORGANIZATION_NAME)),
                name="system_rescue_organization_has_reserved_name",
            ),
        ),
        migrations.AddConstraint(
            model_name="rescueorganization",
            constraint=models.CheckConstraint(
                condition=models.Q(("is_system", True))
                | ~models.Q(("name__iexact", SYSTEM_ORGANIZATION_NAME)),
                name="reserved_name_belongs_to_system_organization",
            ),
        ),
        migrations.AddConstraint(
            model_name="rescueorganization",
            constraint=models.CheckConstraint(
                condition=models.Q(("is_system", False))
                | models.Q(
                    ("created_by__isnull", True),
                    ("is_active", True),
                    ("is_verified", True),
                ),
                name="system_rescue_organization_is_operational",
            ),
        ),
    ]
