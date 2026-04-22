from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, VerifyEmailView,
    ForgotPasswordView, ResetPasswordView, ResendOTPView,
    ProfileView, ChangePasswordView, GoogleLogin
)

urlpatterns = [
    # Auth
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='token_obtain_pair'),
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    # Password
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),

    # Utility
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),

    # Profile
    path('profile/', ProfileView.as_view(), name='profile'),

    # Google OAuth
    path('google/', GoogleLogin.as_view(), name='google-login'),
]