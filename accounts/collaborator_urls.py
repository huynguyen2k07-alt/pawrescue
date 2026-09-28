from django.urls import path

from . import views


app_name = "collaborators"

urlpatterns = [
    path("", views.collaborator_dashboard, name="dashboard"),
]
