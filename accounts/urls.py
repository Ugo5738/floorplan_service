from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from rest_framework import routers
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from accounts import forms, views

router = routers.DefaultRouter()

router.register(r"users", views.UserViewSet, basename="user")

admin_urls = [
    path("", include(router.urls)),
    path("user/", views.CurrentUserDetailView.as_view(), name="current_user"),
]

manual_tokens = [
    path(
        "generate-token/",
        views.GenerateTokenView.as_view(),
        name="generate_auth",
    ),
    path(
        "authenticate-token/",
        views.TokenAuthenticationView.as_view(),
        name="authenticate_auth",
    ),
    path(
        "authenticate-phone/",
        views.PhoneAuthenticationView.as_view(),
        name="authenticate-phone",
    ),
    path(
        "check-authenticated/",
        views.CheckAuthenticatedView.as_view(),
        name="check-authenticated",
    ),
]

jwt_urls = [
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("change-password", views.ChangePasswordView.as_view(), name="change_password"),
    path(
        "password-reset/",
        include("django_rest_passwordreset.urls", namespace="password_reset"),
    ),
]

account_urls = [
    # path("signup/", views.RegisterAPIView.as_view(), name="signup"),
    # path('verify-email/<str:token>/', views.VerifyEmailView.as_view(), name='verify_email'),
    # path('resend-verification/', views.ResendVerificationEmailView.as_view(), name='resend_verification'),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="account/login.html", authentication_form=forms.UserLoginForm
        ),
        name="login",
    ),
    # path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("logout/", views.LogoutView.as_view(), name="auth_logout"),
]

password_urls = [
    # path("change-password/", views.ChangePassword.as_view(), name="change_password"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=forms.CustomPasswordResetForm,
            template_name="account/password/password_reset.html",
            subject_template_name="account/password/password_reset_subject.txt",
            email_template_name="account/password/password_reset_email.html",
            from_email=settings.EMAIL_HOST_USER,
            # success_url='/login/'
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="account/password/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="account/password/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="account/password/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]

urlpatterns = admin_urls + jwt_urls + account_urls + password_urls + manual_tokens

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += staticfiles_urlpatterns()
