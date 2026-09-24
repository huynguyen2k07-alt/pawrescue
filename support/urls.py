from django.urls import path

from . import views


app_name = "support"

urlpatterns = [
    path("chat/state/", views.chat_state, name="chat-state"),
    path("chat/send/", views.chat_send, name="chat-send"),
    path("attachments/<int:pk>/", views.attachment, name="attachment"),
    path("inbox/", views.inbox, name="inbox"),
    path(
        "inbox/cases/<int:pk>/open/",
        views.open_case_chat,
        name="open-case-chat",
    ),
    path("inbox/state/", views.inbox_state, name="inbox-state"),
    path("inbox/<int:pk>/reply/", views.admin_reply, name="admin-reply"),
    path("inbox/<int:pk>/close/", views.close_conversation, name="close"),
]
