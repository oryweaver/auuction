from django.urls import path
from django.urls import reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = "auctions"

urlpatterns = [
    path("", views.catalog_list, name="catalog_list"),
    path("item/<slug:slug>/", views.item_detail, name="item_detail"),
    path("item/<slug:slug>/bid/", views.place_bid, name="place_bid"),
    path("item/<slug:slug>/signup/", views.fixed_price_signup, name="fixed_price_signup"),
    path("item/<slug:slug>/adjust/", views.fixed_price_adjust, name="fixed_price_adjust"),
    path("item/<slug:slug>/cancel/", views.fixed_price_cancel, name="fixed_price_cancel"),
    # Auth
    path("accounts/register/", views.register_view, name="register"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("accounts/profile/", views.profile_complete, name="profile_complete"),
    # Password reset
    path(
        "accounts/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="auctions/password_reset.html",
            email_template_name="auctions/password_reset_email.txt",
            subject_template_name="auctions/password_reset_subject.txt",
            success_url=reverse_lazy("auctions:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="auctions/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="auctions/password_reset_confirm.html",
            success_url=reverse_lazy("auctions:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="auctions/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("accounts/manage/", views.manager_home, name="manager_home"),
    path("accounts/manage/approvals/", views.manager_approvals, name="manager_approvals"),
    path("accounts/manage/items/<slug:slug>/update/", views.manager_update_item, name="manager_update_item"),
    path("accounts/", views.account_home, name="account_home"),
    path("accounts/items/new/", views.donor_item_create, name="donor_item_create"),
    path("accounts/items/<slug:slug>/edit/", views.donor_item_edit, name="donor_item_edit"),
    path("accounts/items/<slug:slug>/publish/", views.manager_publish_item, name="manager_publish_item"),
]
