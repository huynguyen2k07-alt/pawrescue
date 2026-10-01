from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from organizations.models import OrganizationMembership, RescueOrganization
from rescue.models import Notification, RescueCase
from rescue.notifications import create_notifications

from .forms import (
    AdoptionApplicationForm,
    AdoptionCheckInForm,
    AdoptionFollowUpForm,
    AdoptionReviewForm,
    AdoptionSafetyReportForm,
    AdoptionSafetyReviewForm,
    AnimalProfileForm,
)
from .models import (
    AdoptionApplication,
    AdoptionCheckInRequest,
    AdoptionFollowUp,
    AdoptionPlacement,
    AdoptionRestriction,
    AdoptionSafetyReport,
    AnimalProfile,
    AnimalProfileImage,
)


MANAGER_ROLES = (
    OrganizationMembership.Role.OWNER,
    OrganizationMembership.Role.MANAGER,
)


def _managed_organizations(user):
    if not user.is_authenticated:
        return RescueOrganization.objects.none()
    if user.is_superuser:
        return RescueOrganization.objects.filter(
            is_active=True,
            is_verified=True,
        )
    return RescueOrganization.objects.filter(
        memberships__user=user,
        memberships__is_active=True,
        memberships__role__in=MANAGER_ROLES,
        is_active=True,
        is_verified=True,
        is_system=False,
    ).distinct()


def _can_manage_animal(user, animal):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return OrganizationMembership.objects.filter(
        organization=animal.organization,
        organization__is_active=True,
        organization__is_verified=True,
        organization__is_system=False,
        user=user,
        is_active=True,
        role__in=MANAGER_ROLES,
    ).exists()


def _manager_ids(organization):
    manager_ids = set(
        organization.memberships.filter(
            is_active=True,
            role__in=MANAGER_ROLES,
        ).values_list("user_id", flat=True)
    )
    manager_ids.update(
        get_user_model().objects.filter(
            is_active=True,
            is_superuser=True,
        ).values_list("pk", flat=True)
    )
    return manager_ids


def _active_restriction(user, organization):
    return AdoptionRestriction.objects.filter(
        user=user,
        is_active=True,
    ).filter(Q(organization=organization) | Q(organization__isnull=True)).first()


def _restrict_adopter(*, placement, reason, actor, source_report=None):
    organization = None if actor.is_superuser else placement.organization
    restriction, _ = AdoptionRestriction.objects.update_or_create(
        user=placement.adopter,
        organization=organization,
        defaults={
            "reason": reason,
            "source_report": source_report,
            "created_by": actor,
            "is_active": True,
        },
    )
    return restriction


def _save_profile_images(animal, images):
    for image in images:
        AnimalProfileImage.objects.create(animal=animal, image=image)


def _set_adopted_timestamp(animal):
    if animal.status == AnimalProfile.Status.ADOPTED:
        animal.adopted_at = animal.adopted_at or timezone.now()
    else:
        animal.adopted_at = None


def animal_list(request):
    animals = (
        AnimalProfile.objects.filter(
            organization__is_active=True,
            organization__is_verified=True,
        ).exclude(
            status__in=(
                AnimalProfile.Status.ADOPTED,
                AnimalProfile.Status.NOT_AVAILABLE,
            )
        )
        .select_related("organization")
        .prefetch_related("images")
        .annotate(application_count=Count("applications"))
        .order_by("-published_at", "-pk")
    )
    query = request.GET.get("q", "").strip()
    animal_type = request.GET.get("animal_type", "").strip()
    age_group = request.GET.get("age_group", "").strip()
    sex = request.GET.get("sex", "").strip()

    if query:
        animals = animals.filter(
            Q(name__icontains=query)
            | Q(breed__icontains=query)
            | Q(description__icontains=query)
            | Q(location__icontains=query)
        )
    if animal_type in AnimalProfile.AnimalType.values:
        animals = animals.filter(animal_type=animal_type)
    if age_group in AnimalProfile.AgeGroup.values:
        animals = animals.filter(age_group=age_group)
    if sex in AnimalProfile.Sex.values:
        animals = animals.filter(sex=sex)

    context = {
        "page_obj": Paginator(animals, 12).get_page(request.GET.get("page")),
        "query": query,
        "selected_animal_type": animal_type,
        "selected_age_group": age_group,
        "selected_sex": sex,
        "animal_type_choices": AnimalProfile.AnimalType.choices,
        "age_group_choices": AnimalProfile.AgeGroup.choices,
        "sex_choices": AnimalProfile.Sex.choices,
        "can_manage_adoptions": _managed_organizations(request.user).exists(),
    }
    return render(request, "adoptions/animal_list.html", context)


def animal_detail(request, pk):
    animal = get_object_or_404(
        AnimalProfile.objects.select_related(
            "organization",
            "rescue_case",
        ).prefetch_related("images"),
        pk=pk,
        organization__is_active=True,
        organization__is_verified=True,
    )
    existing_application = None
    if request.user.is_authenticated:
        existing_application = animal.applications.filter(
            applicant=request.user
        ).select_related("placement").first()
    context = {
        "animal": animal,
        "can_manage": _can_manage_animal(request.user, animal),
        "can_apply": animal.status == AnimalProfile.Status.AVAILABLE,
        "existing_application": existing_application,
        "application_form": AdoptionApplicationForm(user=request.user),
        "active_placement": animal.placements.filter(is_active=True).first(),
    }
    return render(request, "adoptions/animal_detail.html", context)


@login_required
def animal_create(request):
    if not _managed_organizations(request.user).exists():
        return HttpResponseForbidden(
            "Bạn cần là chủ hoặc điều phối viên của một tổ chức cứu hộ."
        )

    if request.method == "POST":
        form = AnimalProfileForm(
            request.POST,
            request.FILES,
            user=request.user,
            require_images=True,
        )
        if form.is_valid():
            with transaction.atomic():
                animal = form.save(commit=False)
                animal.created_by = request.user
                _set_adopted_timestamp(animal)
                animal.save()
                _save_profile_images(animal, form.cleaned_data["images"])
            messages.success(request, "Hồ sơ nhận nuôi đã được đăng.")
            return redirect("adoptions:animal-detail", pk=animal.pk)
    else:
        form = AnimalProfileForm(user=request.user, require_images=True)
        case_id = request.GET.get("case")
        if case_id:
            rescue_case = form.fields["rescue_case"].queryset.filter(pk=case_id).first()
            if rescue_case:
                form.initial.update(
                    {
                        "rescue_case": rescue_case,
                        "organization": rescue_case.organization,
                        "animal_type": (
                            rescue_case.animal_type
                            if rescue_case.animal_type
                            in AnimalProfile.AnimalType.values
                            else AnimalProfile.AnimalType.OTHER
                        ),
                        "description": rescue_case.description,
                        "location": rescue_case.organization.address
                        or rescue_case.address,
                    }
                )

    return render(
        request,
        "adoptions/animal_form.html",
        {"form": form, "is_create": True},
    )


@login_required
def animal_update(request, pk):
    animal = get_object_or_404(AnimalProfile, pk=pk)
    if not _can_manage_animal(request.user, animal):
        return HttpResponseForbidden("Bạn không có quyền sửa hồ sơ này.")

    if request.method == "POST":
        form = AnimalProfileForm(
            request.POST,
            request.FILES,
            instance=animal,
            user=request.user,
        )
        if form.is_valid():
            with transaction.atomic():
                animal = form.save(commit=False)
                _set_adopted_timestamp(animal)
                animal.save()
                _save_profile_images(animal, form.cleaned_data["images"])
            messages.success(request, "Hồ sơ nhận nuôi đã được cập nhật.")
            return redirect("adoptions:animal-detail", pk=animal.pk)
    else:
        form = AnimalProfileForm(instance=animal, user=request.user)

    return render(
        request,
        "adoptions/animal_form.html",
        {"form": form, "animal": animal, "is_create": False},
    )


@require_POST
@login_required
def application_create(request, pk):
    with transaction.atomic():
        animal = get_object_or_404(
            AnimalProfile.objects.select_for_update().select_related("organization"),
            pk=pk,
            organization__is_active=True,
            organization__is_verified=True,
        )
        if animal.status != AnimalProfile.Status.AVAILABLE:
            messages.error(request, "Hồ sơ này hiện không nhận thêm đơn.")
            return redirect("adoptions:animal-detail", pk=pk)
        restriction = _active_restriction(request.user, animal.organization)
        if restriction:
            messages.error(
                request,
                "Tài khoản của bạn đang bị tạm ngừng đăng ký nhận nuôi. "
                "Hãy liên hệ tổ chức phụ trách để được xem xét.",
            )
            return redirect("adoptions:animal-detail", pk=pk)
        if AdoptionApplication.objects.filter(
            animal=animal,
            applicant=request.user,
        ).exists():
            messages.info(request, "Bạn đã gửi đơn cho hồ sơ này rồi.")
            return redirect("adoptions:my-applications")

        form = AdoptionApplicationForm(request.POST, user=request.user)
        if not form.is_valid():
            errors = [
                str(error)
                for field_errors in form.errors.values()
                for error in field_errors
            ]
            messages.error(
                request,
                errors[0] if errors else "Không thể gửi đơn. Hãy kiểm tra lại.",
            )
            return redirect("adoptions:animal-detail", pk=pk)

        application = form.save(commit=False)
        application.animal = animal
        application.applicant = request.user
        application.pledge_accepted_at = timezone.now()
        application.save()
        create_notifications(
            recipient_ids=_manager_ids(animal.organization),
            kind=Notification.Kind.ADOPTION_SUBMITTED,
            title="Có đơn nhận nuôi mới",
            message=(
                f'{application.applicant_name} vừa gửi đơn nhận nuôi "{animal.name}".'
            ),
            actor=request.user,
            target_url=reverse("adoptions:dashboard"),
        )

    messages.success(request, "Đơn nhận nuôi đã được gửi tới tổ chức phụ trách.")
    return redirect("adoptions:my-applications")


@login_required
def my_applications(request):
    applications = request.user.adoption_applications.select_related(
        "animal",
        "animal__organization",
        "placement",
    ).prefetch_related("animal__images", "placement__check_in_requests")
    return render(
        request,
        "adoptions/my_applications.html",
        {"applications": applications},
    )


@require_POST
@login_required
def application_withdraw(request, pk):
    with transaction.atomic():
        application = get_object_or_404(
            AdoptionApplication.objects.select_for_update().select_related("animal"),
            pk=pk,
            applicant=request.user,
        )
        if application.status not in {
            AdoptionApplication.Status.PENDING,
            AdoptionApplication.Status.REVIEWING,
        }:
            messages.error(request, "Đơn này không thể rút ở trạng thái hiện tại.")
            return redirect("adoptions:my-applications")
        application.status = AdoptionApplication.Status.WITHDRAWN
        application.reviewed_at = timezone.now()
        application.save(update_fields=("status", "reviewed_at"))
        if (
            application.animal.status == AnimalProfile.Status.PENDING
            and not application.animal.applications.exclude(pk=application.pk).filter(
                status__in=(
                    AdoptionApplication.Status.PENDING,
                    AdoptionApplication.Status.REVIEWING,
                )
            ).exists()
        ):
            application.animal.status = AnimalProfile.Status.AVAILABLE
            application.animal.save(update_fields=("status", "updated_at"))
    messages.success(request, "Bạn đã rút đơn nhận nuôi.")
    return redirect("adoptions:my-applications")


@login_required
def dashboard(request):
    organizations = _managed_organizations(request.user)
    if not organizations.exists():
        return HttpResponseForbidden(
            "Bạn cần là chủ hoặc điều phối viên để xét duyệt đơn nhận nuôi."
        )
    selected_status = request.GET.get("status", "").strip()
    applications = AdoptionApplication.objects.filter(
        animal__organization__in=organizations
    ).select_related("animal", "applicant", "animal__organization")
    if selected_status in AdoptionApplication.Status.values:
        applications = applications.filter(status=selected_status)
    profiles = (
        AnimalProfile.objects.filter(organization__in=organizations)
        .select_related("organization")
        .prefetch_related("images")
        .annotate(application_count=Count("applications"))
    )
    placements = AdoptionPlacement.objects.filter(
        organization__in=organizations,
        is_active=True,
    ).select_related("animal", "adopter", "application", "organization")
    safety_reports = AdoptionSafetyReport.objects.filter(
        animal__organization__in=organizations,
    ).select_related("animal", "placement", "reporter", "reviewed_by")[:30]
    check_in_requests = AdoptionCheckInRequest.objects.filter(
        placement__organization__in=organizations,
    ).select_related("placement__animal", "placement__adopter")
    due_follow_ups = check_in_requests.filter(
        due_on__lte=timezone.localdate(),
        submitted_at__isnull=True,
        placement__is_active=True,
    ).count()
    context = {
        "applications": applications,
        "profiles": profiles,
        "selected_status": selected_status,
        "status_choices": AdoptionApplication.Status.choices,
        "review_status_choices": AdoptionReviewForm.base_fields["status"].choices,
        "placements": placements,
        "safety_reports": safety_reports,
        "due_follow_ups": due_follow_ups,
        "recent_check_ins": check_in_requests.filter(
            submitted_at__isnull=False,
        ).order_by("-submitted_at")[:12],
        "follow_up_contact_choices": AdoptionFollowUp.ContactMethod.choices,
        "follow_up_outcome_choices": AdoptionFollowUp.Outcome.choices,
        "safety_review_status_choices": AdoptionSafetyReviewForm.base_fields[
            "status"
        ].choices,
    }
    return render(request, "adoptions/dashboard.html", context)


@require_POST
@login_required
def application_review(request, pk):
    form = AdoptionReviewForm(request.POST)
    if not form.is_valid():
        errors = [
            str(error)
            for field_errors in form.errors.values()
            for error in field_errors
        ]
        messages.error(
            request,
            errors[0] if errors else "Kết quả xét duyệt không hợp lệ.",
        )
        return redirect("adoptions:dashboard")

    with transaction.atomic():
        application = get_object_or_404(
            AdoptionApplication.objects.select_for_update().select_related(
                "animal",
                "animal__organization",
                "applicant",
            ),
            pk=pk,
        )
        if not _can_manage_animal(request.user, application.animal):
            return HttpResponseForbidden("Bạn không có quyền xét duyệt đơn này.")
        if application.status in {
            AdoptionApplication.Status.APPROVED,
            AdoptionApplication.Status.REJECTED,
            AdoptionApplication.Status.WITHDRAWN,
        }:
            messages.info(request, "Đơn này đã được xử lý trước đó.")
            return redirect("adoptions:dashboard")

        new_status = form.cleaned_data["status"]
        now = timezone.now()
        application.status = new_status
        application.review_note = form.cleaned_data["review_note"]
        application.reviewer = request.user
        application.reviewed_at = now
        application.save(
            update_fields=(
                "status",
                "review_note",
                "reviewer",
                "reviewed_at",
            )
        )

        animal = AnimalProfile.objects.select_for_update().get(pk=application.animal_id)
        if new_status == AdoptionApplication.Status.APPROVED:
            application.identity_verified_at = now
            application.save(update_fields=("identity_verified_at",))
            animal.status = AnimalProfile.Status.ADOPTED
            animal.adopted_at = now
            animal.save(update_fields=("status", "adopted_at", "updated_at"))
            other_applications = list(
                animal.applications.select_for_update()
                .exclude(pk=application.pk)
                .filter(
                    status__in=(
                        AdoptionApplication.Status.PENDING,
                        AdoptionApplication.Status.REVIEWING,
                    )
                )
            )
            for other in other_applications:
                other.status = AdoptionApplication.Status.REJECTED
                other.reviewer = request.user
                other.reviewed_at = now
                other.review_note = "Hồ sơ đã tìm được gia đình phù hợp."
            AdoptionApplication.objects.bulk_update(
                other_applications,
                ("status", "reviewer", "reviewed_at", "review_note"),
            )
            create_notifications(
                recipient_ids=(other.applicant_id for other in other_applications),
                kind=Notification.Kind.ADOPTION_REVIEWED,
                title="Cập nhật đơn nhận nuôi",
                message=(
                    f'"{animal.name}" đã tìm được gia đình phù hợp. '
                    "Cảm ơn bạn đã quan tâm."
                ),
                actor=request.user,
                target_url=reverse("adoptions:my-applications"),
            )
            AdoptionPlacement.objects.update_or_create(
                application=application,
                defaults={
                    "animal": animal,
                    "adopter": application.applicant,
                    "organization": animal.organization,
                    "status": AdoptionPlacement.Status.ACTIVE,
                    "placed_at": now,
                    "next_follow_up_on": None,
                    "is_active": True,
                },
            )
        elif new_status == AdoptionApplication.Status.REVIEWING:
            animal.status = AnimalProfile.Status.PENDING
            animal.save(update_fields=("status", "updated_at"))
        elif (
            animal.status == AnimalProfile.Status.PENDING
            and not animal.applications.exclude(pk=application.pk).filter(
                status__in=(
                    AdoptionApplication.Status.PENDING,
                    AdoptionApplication.Status.REVIEWING,
                )
            ).exists()
        ):
            animal.status = AnimalProfile.Status.AVAILABLE
            animal.save(update_fields=("status", "updated_at"))

        create_notifications(
            recipient_ids=(application.applicant_id,),
            kind=Notification.Kind.ADOPTION_REVIEWED,
            title="Đơn nhận nuôi đã được cập nhật",
            message=(
                f'Đơn nhận nuôi "{animal.name}" hiện ở trạng thái '
                f'“{application.get_status_display()}”.'
            ),
            actor=request.user,
            target_url=reverse("adoptions:my-applications"),
        )

    messages.success(request, "Đơn nhận nuôi đã được cập nhật.")
    return redirect("adoptions:dashboard")


@login_required
def check_in(request, pk):
    check_in_request = get_object_or_404(
        AdoptionCheckInRequest.objects.select_related(
            "placement__animal",
            "placement__organization",
            "placement__adopter",
        ),
        pk=pk,
        placement__adopter=request.user,
    )
    if check_in_request.submitted_at:
        messages.info(request, "Bạn đã gửi cập nhật cho mốc theo dõi này rồi.")
        return redirect("adoptions:my-applications")

    if request.method == "POST":
        form = AdoptionCheckInForm(request.POST, instance=check_in_request)
        if form.is_valid():
            with transaction.atomic():
                locked = get_object_or_404(
                    AdoptionCheckInRequest.objects.select_for_update().select_related(
                        "placement__animal",
                        "placement__organization",
                        "placement__adopter",
                    ),
                    pk=check_in_request.pk,
                    placement__adopter=request.user,
                    submitted_at__isnull=True,
                )
                locked_form = AdoptionCheckInForm(request.POST, instance=locked)
                if not locked_form.is_valid():
                    form = locked_form
                else:
                    completed = locked_form.save(commit=False)
                    completed.submitted_at = timezone.now()
                    completed.save()

                    placement = completed.placement
                    needs_attention = (
                        completed.care_status
                        != AdoptionCheckInRequest.CareStatus.IN_CARE
                        or completed.wellbeing
                        in {
                            AdoptionCheckInRequest.Wellbeing.CONCERNING,
                            AdoptionCheckInRequest.Wellbeing.URGENT,
                        }
                    )
                    placement.last_follow_up_at = completed.submitted_at
                    placement.status = (
                        AdoptionPlacement.Status.NEEDS_ATTENTION
                        if needs_attention
                        else AdoptionPlacement.Status.ACTIVE
                    )
                    placement.next_follow_up_on = (
                        placement.check_in_requests.filter(
                            submitted_at__isnull=True,
                        )
                        .order_by("due_on")
                        .values_list("due_on", flat=True)
                        .first()
                    )
                    placement.save(
                        update_fields=(
                            "status",
                            "last_follow_up_at",
                            "next_follow_up_on",
                            "updated_at",
                        )
                    )

                    outcome = (
                        AdoptionFollowUp.Outcome.NEEDS_ATTENTION
                        if needs_attention
                        else AdoptionFollowUp.Outcome.WELL
                    )
                    AdoptionFollowUp.objects.create(
                        placement=placement,
                        created_by=request.user,
                        contact_method=AdoptionFollowUp.ContactMethod.MESSAGE,
                        outcome=outcome,
                        notes=(
                            f"Cập nhật tháng {completed.milestone_month}: "
                            f"{completed.get_care_status_display()}; "
                            f"{completed.get_wellbeing_display()}. "
                            f"{completed.care_summary} {completed.health_changes}"
                        ).strip(),
                        contacted_at=completed.submitted_at,
                    )
                    create_notifications(
                        recipient_ids=_manager_ids(placement.organization),
                        kind=Notification.Kind.ADOPTION_FOLLOW_UP,
                        title=f"Có cập nhật mới về {placement.animal.name}",
                        message=(
                            f"Người nhận nuôi đã gửi phản hồi tháng "
                            f"{completed.milestone_month}."
                            + (" Cần kiểm tra sớm." if needs_attention else "")
                        ),
                        actor=request.user,
                        target_url=reverse("adoptions:dashboard"),
                    )
                    messages.success(
                        request,
                        "Cảm ơn bạn. Tình hình của pet đã được gửi tới tổ chức phụ trách.",
                    )
                    return redirect("adoptions:my-applications")
    else:
        form = AdoptionCheckInForm(instance=check_in_request)

    return render(
        request,
        "adoptions/check_in_form.html",
        {"check_in": check_in_request, "form": form},
    )


@login_required
def safety_report_create(request, pk):
    animal = get_object_or_404(
        AnimalProfile.objects.select_related("organization"),
        pk=pk,
        organization__is_active=True,
        organization__is_verified=True,
    )
    if request.method == "POST":
        form = AdoptionSafetyReportForm(request.POST)
        if form.is_valid():
            existing = AdoptionSafetyReport.objects.filter(
                animal=animal,
                reporter=request.user,
                status__in=(
                    AdoptionSafetyReport.Status.PENDING,
                    AdoptionSafetyReport.Status.REVIEWING,
                ),
            ).first()
            if existing:
                messages.info(
                    request,
                    "Báo cáo trước của bạn đang được xác minh. Cảm ơn bạn đã cung cấp thông tin.",
                )
                return redirect("adoptions:animal-detail", pk=animal.pk)

            report = form.save(commit=False)
            report.animal = animal
            report.reporter = request.user
            report.placement = animal.placements.filter(is_active=True).first()
            report.save()
            create_notifications(
                recipient_ids=_manager_ids(animal.organization),
                kind=Notification.Kind.ADOPTION_SAFETY,
                title="Có báo cáo an toàn nhận nuôi",
                message=f'Có báo cáo mới liên quan đến "{animal.name}" cần xác minh.',
                actor=request.user,
                target_url=reverse("adoptions:dashboard"),
            )
            messages.success(
                request,
                "Báo cáo đã được gửi riêng tới tổ chức phụ trách để xác minh.",
            )
            return redirect("adoptions:animal-detail", pk=animal.pk)
    else:
        form = AdoptionSafetyReportForm()
    return render(
        request,
        "adoptions/safety_report_form.html",
        {"animal": animal, "form": form},
    )


@require_POST
@login_required
def safety_report_review(request, pk):
    form = AdoptionSafetyReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Kết quả xác minh chưa hợp lệ.")
        return redirect("adoptions:dashboard")

    with transaction.atomic():
        report = get_object_or_404(
            AdoptionSafetyReport.objects.select_for_update().select_related(
                "animal",
                "animal__organization",
                "placement",
                "placement__adopter",
            ),
            pk=pk,
        )
        if not _can_manage_animal(request.user, report.animal):
            return HttpResponseForbidden("Bạn không có quyền xử lý báo cáo này.")

        report.status = form.cleaned_data["status"]
        report.review_note = form.cleaned_data["review_note"]
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.save(
            update_fields=("status", "review_note", "reviewed_by", "reviewed_at")
        )

        if (
            report.status == AdoptionSafetyReport.Status.CONFIRMED
            and report.placement
        ):
            report.placement.status = AdoptionPlacement.Status.FLAGGED
            report.placement.save(update_fields=("status", "updated_at"))
            _restrict_adopter(
                placement=report.placement,
                reason=(
                    f"Vi phạm cam kết nhận nuôi liên quan đến {report.animal.name}. "
                    f"{report.review_note}"
                ).strip(),
                actor=request.user,
                source_report=report,
            )

        if report.reporter_id:
            create_notifications(
                recipient_ids=(report.reporter_id,),
                kind=Notification.Kind.ADOPTION_SAFETY,
                title="Báo cáo an toàn đã được cập nhật",
                message=(
                    f'Báo cáo liên quan đến "{report.animal.name}" hiện ở trạng thái '
                    f'“{report.get_status_display()}”.'
                ),
                actor=request.user,
                target_url=reverse("adoptions:animal-detail", args=(report.animal_id,)),
            )

    messages.success(request, "Báo cáo an toàn đã được cập nhật.")
    return redirect("adoptions:dashboard")


@require_POST
@login_required
def placement_follow_up(request, pk):
    form = AdoptionFollowUpForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Thông tin theo dõi chưa hợp lệ.")
        return redirect("adoptions:dashboard")

    with transaction.atomic():
        placement = get_object_or_404(
            AdoptionPlacement.objects.select_for_update().select_related(
                "animal",
                "organization",
                "adopter",
            ),
            pk=pk,
        )
        if not _can_manage_animal(request.user, placement.animal):
            return HttpResponseForbidden("Bạn không có quyền theo dõi hồ sơ này.")

        follow_up = form.save(commit=False)
        follow_up.placement = placement
        follow_up.created_by = request.user
        follow_up.save()

        placement.last_follow_up_at = follow_up.contacted_at
        placement.next_follow_up_on = (
            placement.check_in_requests.filter(submitted_at__isnull=True)
            .order_by("due_on")
            .values_list("due_on", flat=True)
            .first()
        )
        if follow_up.outcome == AdoptionFollowUp.Outcome.WELL:
            placement.status = AdoptionPlacement.Status.ACTIVE
        elif follow_up.outcome in {
            AdoptionFollowUp.Outcome.NEEDS_ATTENTION,
            AdoptionFollowUp.Outcome.UNREACHABLE,
        }:
            placement.status = AdoptionPlacement.Status.NEEDS_ATTENTION
        elif follow_up.outcome == AdoptionFollowUp.Outcome.SUSPECTED_RESALE:
            placement.status = AdoptionPlacement.Status.FLAGGED
            _restrict_adopter(
                placement=placement,
                reason=(
                    f"Theo dõi sau nhận nuôi ghi nhận nghi ngờ mua bán/chuyển nhượng "
                    f"{placement.animal.name}. {follow_up.notes}"
                ),
                actor=request.user,
            )
        elif follow_up.outcome == AdoptionFollowUp.Outcome.RETURNED:
            placement.status = AdoptionPlacement.Status.RETURNED
            placement.is_active = False
            placement.next_follow_up_on = None
            placement.animal.status = AnimalProfile.Status.HOLD
            placement.animal.adopted_at = None
            placement.animal.save(
                update_fields=("status", "adopted_at", "updated_at")
            )
        placement.save(
            update_fields=(
                "status",
                "is_active",
                "last_follow_up_at",
                "next_follow_up_on",
                "updated_at",
            )
        )

    messages.success(request, "Đã lưu kết quả theo dõi sau nhận nuôi.")
    return redirect("adoptions:dashboard")
