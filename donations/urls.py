from django.urls import path

from . import views


app_name = "donations"

urlpatterns = [
    path("", views.campaign_list, name="campaign-list"),
    path("new/", views.campaign_create, name="campaign-create"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("mine/", views.my_donations, name="my-donations"),
    path(
        "donations/<int:pk>/proof/",
        views.donation_proof,
        name="donation-proof",
    ),
    path(
        "expenses/<int:pk>/receipt/",
        views.expense_receipt,
        name="expense-receipt",
    ),
    path("<int:pk>/", views.campaign_detail, name="campaign-detail"),
    path("<int:pk>/edit/", views.campaign_update, name="campaign-update"),
    path("<int:pk>/donate/", views.donation_create, name="donation-create"),
    path(
        "<int:campaign_pk>/expenses/new/",
        views.expense_create,
        name="expense-create",
    ),
    path(
        "donations/<int:pk>/review/",
        views.donation_review,
        name="donation-review",
    ),
]
