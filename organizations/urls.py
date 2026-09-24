from django.urls import path

from . import views

app_name = "organizations"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("new/", views.organization_create, name="organization-create"),
    path("<int:pk>/", views.organization_detail, name="organization-detail"),
    path("<int:pk>/edit/", views.organization_update, name="organization-update"),
    path("<int:pk>/members/add/", views.member_add, name="member-add"),
    path(
        "<int:pk>/members/<int:membership_pk>/role/",
        views.member_change_role,
        name="member-change-role",
    ),
    path(
        "<int:pk>/members/<int:membership_pk>/remove/",
        views.member_remove,
        name="member-remove",
    ),
]
