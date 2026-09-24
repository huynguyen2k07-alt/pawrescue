from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect("rescue:case-list")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Tài khoản của bạn đã được tạo.")
            return redirect("rescue:case-list")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    context = {
        "reported_count": request.user.reported_rescue_cases.count(),
        "assignment_count": request.user.rescue_assignments.filter(
            is_active=True
        ).count(),
        "organization_count": request.user.organization_memberships.filter(
            is_active=True
        ).count(),
    }
    return render(request, "accounts/profile.html", context)
