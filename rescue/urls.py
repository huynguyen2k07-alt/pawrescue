from django.urls import path

from . import views

app_name = "rescue"

urlpatterns = [
    path("", views.case_list, name="case-list"),
    path("map/", views.case_map, name="case-map"),
    path("knowledge/", views.knowledge_list, name="knowledge-list"),
    path(
        "knowledge/<slug:slug>/",
        views.knowledge_detail,
        name="knowledge-detail",
    ),
    path("cases/new/", views.case_create, name="case-create"),
    path("cases/mine/", views.my_cases, name="my-cases"),
    path("cases/<int:pk>/", views.case_detail, name="case-detail"),
    path("cases/<int:pk>/claim/", views.case_claim, name="case-claim"),
    path(
        "cases/<int:pk>/status/",
        views.case_update_status,
        name="case-update-status",
    ),
    path("cases/<int:pk>/assign/", views.case_assign, name="case-assign"),
    path(
        "cases/<int:pk>/updates/new/",
        views.case_add_update,
        name="case-add-update",
    ),
    path("notifications/", views.notification_list, name="notification-list"),
    path(
        "notifications/<int:pk>/open/",
        views.notification_open,
        name="notification-open",
    ),
    path(
        "notifications/read-all/",
        views.notification_read_all,
        name="notification-read-all",
    ),
]
