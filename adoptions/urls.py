from django.urls import path

from . import views


app_name = "adoptions"

urlpatterns = [
    path("", views.animal_list, name="animal-list"),
    path("new/", views.animal_create, name="animal-create"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("applications/mine/", views.my_applications, name="my-applications"),
    path(
        "applications/<int:pk>/withdraw/",
        views.application_withdraw,
        name="application-withdraw",
    ),
    path(
        "applications/<int:pk>/review/",
        views.application_review,
        name="application-review",
    ),
    path(
        "safety-reports/<int:pk>/review/",
        views.safety_report_review,
        name="safety-report-review",
    ),
    path(
        "placements/<int:pk>/follow-up/",
        views.placement_follow_up,
        name="placement-follow-up",
    ),
    path("<int:pk>/", views.animal_detail, name="animal-detail"),
    path("<int:pk>/edit/", views.animal_update, name="animal-update"),
    path("<int:pk>/apply/", views.application_create, name="application-create"),
    path(
        "<int:pk>/report-safety/",
        views.safety_report_create,
        name="safety-report-create",
    ),
]
