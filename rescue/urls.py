from django.urls import path

from . import views
from .notification_live import notification_state
from .geocoding import address_search
from .statistics import public_statistics_state

app_name = "rescue"

urlpatterns = [
    path("", views.case_list, name="case-list"),
    path("map/", views.case_map, name="case-map"),
    path("statistics/live/", public_statistics_state, name="public-statistics-live"),
    path("knowledge/", views.knowledge_list, name="knowledge-list"),
    path("team/", views.team, name="team"),
    path(
        "knowledge/<slug:slug>/",
        views.knowledge_detail,
        name="knowledge-detail",
    ),
    path("cases/new/", views.case_create, name="case-create"),
    path("locations/search/", address_search, name="location-search"),
    path("cases/mine/", views.my_cases, name="my-cases"),
    path("case-images/<int:pk>/", views.case_image, name="case-image"),
    path("update-images/<int:pk>/", views.update_image, name="update-image"),
    path("cases/<int:pk>/", views.case_detail, name="case-detail"),
    path("cases/<int:pk>/messages/", views.case_messages, name="case-messages"),
    path("cases/<int:pk>/notify-admins/", views.case_notify_admins, name="case-notify-admins"),
    path("cases/<int:pk>/reject/", views.case_reject, name="case-reject"),
    path("cases/<int:pk>/claim/", views.case_claim, name="case-claim"),
    path("cases/<int:pk>/handoff/", views.case_handoff, name="case-handoff"),
    path(
        "cases/<int:pk>/status/",
        views.case_update_status,
        name="case-update-status",
    ),
    path("cases/<int:pk>/assign/", views.case_assign, name="case-assign"),
    path("cases/<int:pk>/assignments/<int:assignment_pk>/end/", views.case_unassign, name="case-unassign"),
    path(
        "cases/<int:pk>/updates/new/",
        views.case_add_update,
        name="case-add-update",
    ),
    path("notifications/", views.notification_list, name="notification-list"),
    path("notifications/state/", notification_state, name="notification-state"),
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
