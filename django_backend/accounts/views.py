from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth import get_user_model
from django.utils.decorators import method_decorator

from django_ratelimit.decorators import ratelimit

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
)

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView

from .models import OTPCode
from .serializers import (
    RegisterSerializer,
    VerifyEmailSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ResendOTPSerializer,
    ChangePasswordSerializer,
    UserSerializer,
)
from .emails import send_otp_email

User = get_user_model()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_tokens_for_user(user):
    """Generate JWT access and refresh tokens for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def ratelimit_error_response():
    """Standard response when rate limit is exceeded."""
    return Response(
        {
            "error": "Too many requests. Please wait before trying again.",
            "code": "rate_limit_exceeded",
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


# ─── Register ─────────────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="5/h", method="POST", block=False),
    name="post",
)
class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Register a new user",
        description=(
            "Creates a new user account and sends a **4-digit OTP** to the provided "
            "email address for verification.\n\n"
            "After registration, call `/verify-email/` with the OTP to activate the account."
        ),
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(description="Account created. OTP sent to email."),
            400: OpenApiResponse(description="Validation errors (e.g. email taken, passwords mismatch)."),
            429: OpenApiResponse(description="Rate limit exceeded. Max 5 registrations per hour per IP."),
        },
        examples=[
            OpenApiExample(
                "Valid registration",
                value={
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john@example.com",
                    "password": "StrongPass123!",
                    "confirm_password": "StrongPass123!",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return ratelimit_error_response()

        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            otp = OTPCode.generate_otp(user, "verify_email")
            send_otp_email(user, otp.code, "verify_email")
            return Response(
                {
                    "message": f"Account created! A 4-digit OTP has been sent to {user.email}.",
                    "email": user.email,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Verify Email ─────────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="10/h", method="POST", block=False),
    name="post",
)
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["OTP"],
        summary="Verify email with OTP",
        description=(
            "Verifies the **4-digit OTP** sent to the user's email during registration.\n\n"
            "On success, the account is activated and JWT tokens are returned so "
            "the user is logged in immediately.\n\n"
            "OTP expires after **10 minutes**. Use `/resend-otp/` if it expires."
        ),
        request=VerifyEmailSerializer,
        responses={
            200: OpenApiResponse(description="Email verified. JWT access + refresh tokens returned."),
            400: OpenApiResponse(description="Invalid or expired OTP."),
            429: OpenApiResponse(description="Rate limit exceeded. Max 10 attempts per hour per IP."),
        },
        examples=[
            OpenApiExample(
                "Valid OTP verification",
                value={"email": "john@example.com", "code": "4821"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return ratelimit_error_response()

        serializer = VerifyEmailSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            otp = serializer.validated_data["otp"]

            user.is_verified = True
            user.save()
            otp.is_used = True
            otp.save()

            tokens = get_tokens_for_user(user)
            return Response(
                {
                    "message": "Email verified successfully!",
                    "user": UserSerializer(user).data,
                    **tokens,
                }
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Login ────────────────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="10/h", method="POST", block=False),
    name="post",
)
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Login",
        description=(
            "Authenticates a verified user and returns JWT **access** and **refresh** tokens.\n\n"
            "- Access token expires in **60 minutes**\n"
            "- Refresh token expires in **7 days**\n\n"
            "Use the access token as: `Authorization: Bearer <access_token>` "
            "on all protected endpoints."
        ),
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Login successful. JWT tokens returned."),
            400: OpenApiResponse(description="Invalid credentials or unverified email."),
            429: OpenApiResponse(description="Rate limit exceeded. Max 10 attempts per hour per IP."),
        },
        examples=[
            OpenApiExample(
                "Valid login",
                value={"email": "john@example.com", "password": "StrongPass123!"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return ratelimit_error_response()

        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            tokens = get_tokens_for_user(user)
            return Response(
                {
                    "message": "Login successful!",
                    "user": UserSerializer(user).data,
                    **tokens,
                }
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Forgot Password ──────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="5/h", method="POST", block=False),
    name="post",
)
class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Password"],
        summary="Forgot password — request OTP",
        description=(
            "Sends a **4-digit OTP** to the provided email for password reset.\n\n"
            "Always returns HTTP 200 regardless of whether the email exists "
            "to prevent **email enumeration attacks**.\n\n"
            "Follow up with `/reset-password/` using the received OTP."
        ),
        request=ForgotPasswordSerializer,
        responses={
            200: OpenApiResponse(description="OTP sent if a verified account exists for that email."),
            429: OpenApiResponse(description="Rate limit exceeded. Max 5 requests per hour per IP."),
        },
        examples=[
            OpenApiExample(
                "Example",
                value={"email": "john@example.com"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return ratelimit_error_response()

        serializer = ForgotPasswordSerializer(data=request.data, context={})
        if serializer.is_valid():
            user = serializer.context.get("user")
            if user:
                otp = OTPCode.generate_otp(user, "reset_password")
                send_otp_email(user, otp.code, "reset_password")

        # Always return the same message — never reveal if email exists
        return Response(
            {"message": "If an account with that email exists, a reset OTP has been sent."}
        )


# ─── Reset Password ───────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="10/h", method="POST", block=False),
    name="post",
)
class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Password"],
        summary="Reset password with OTP",
        description=(
            "Verifies the **4-digit OTP** received via email and sets a new password.\n\n"
            "The OTP is **single-use** and expires after **10 minutes**."
        ),
        request=ResetPasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successful."),
            400: OpenApiResponse(description="Invalid or expired OTP, or passwords do not match."),
            429: OpenApiResponse(description="Rate limit exceeded. Max 10 attempts per hour per IP."),
        },
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "email": "john@example.com",
                    "code": "3947",
                    "new_password": "NewStrongPass123!",
                    "confirm_password": "NewStrongPass123!",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return ratelimit_error_response()

        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            otp = serializer.validated_data["otp"]

            user.set_password(serializer.validated_data["new_password"])
            user.save()
            otp.is_used = True
            otp.save()

            return Response({"message": "Password reset successful! You can now log in."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Resend OTP ───────────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="3/h", method="POST", block=False),
    name="post",
)
class ResendOTPView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["OTP"],
        summary="Resend OTP",
        description=(
            "Generates and sends a fresh **4-digit OTP** to the user's email.\n\n"
            "Any previous unused OTP of the same type is invalidated immediately.\n\n"
            "**otp_type values:**\n"
            "- `verify_email` — use after registration if OTP expired\n"
            "- `reset_password` — use during forgot password flow if OTP expired\n\n"
            "⚠️ Strictly rate limited to **3 requests per hour** to prevent OTP spam."
        ),
        request=ResendOTPSerializer,
        responses={
            200: OpenApiResponse(description="New OTP sent successfully."),
            400: OpenApiResponse(description="Invalid email or otp_type."),
            429: OpenApiResponse(description="Rate limit exceeded. Max 3 resends per hour per IP."),
        },
        examples=[
            OpenApiExample(
                "Resend for email verification",
                value={"email": "john@example.com", "otp_type": "verify_email"},
                request_only=True,
            ),
            OpenApiExample(
                "Resend for password reset",
                value={"email": "john@example.com", "otp_type": "reset_password"},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return ratelimit_error_response()

        serializer = ResendOTPSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            otp_type = serializer.validated_data["otp_type"]
            user = User.objects.get(email=email)

            otp = OTPCode.generate_otp(user, otp_type)
            send_otp_email(user, otp.code, otp_type)

            return Response({"message": f"A new OTP has been sent to {email}."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Profile ──────────────────────────────────────────────────────────────────

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Profile"],
        summary="Get my profile",
        description="Returns the authenticated user's full profile details.",
        responses={
            200: UserSerializer,
            401: OpenApiResponse(description="Authentication credentials not provided."),
        },
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        tags=["Profile"],
        summary="Update my profile",
        description=(
            "Partially updates the authenticated user's profile.\n\n"
            "Updatable fields: `first_name`, `last_name`, `avatar`.\n\n"
            "Email and verification status cannot be changed here."
        ),
        request=UserSerializer,
        responses={
            200: UserSerializer,
            400: OpenApiResponse(description="Validation errors."),
            401: OpenApiResponse(description="Authentication credentials not provided."),
        },
    )
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Change Password ──────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="5/h", method="POST", block=False),
    name="post",
)
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Password"],
        summary="Change password",
        description=(
            "Changes the password for the currently authenticated user.\n\n"
            "Requires the existing password for verification before setting the new one."
        ),
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password changed successfully."),
            400: OpenApiResponse(description="Old password incorrect or new passwords do not match."),
            401: OpenApiResponse(description="Authentication credentials not provided."),
            429: OpenApiResponse(description="Rate limit exceeded. Max 5 attempts per hour per IP."),
        },
        examples=[
            OpenApiExample(
                "Example",
                value={
                    "old_password": "OldPass123!",
                    "new_password": "NewStrongPass456!",
                    "confirm_password": "NewStrongPass456!",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return ratelimit_error_response()

        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data["old_password"]):
                return Response(
                    {"error": "Old password is incorrect."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.set_password(serializer.validated_data["new_password"])
            user.save()
            return Response({"message": "Password changed successfully."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Google OAuth ─────────────────────────────────────────────────────────────

class GoogleLogin(SocialLoginView):
    """Google OAuth2 login — exchange a Google access token for JWT tokens."""

    adapter_class = GoogleOAuth2Adapter
    callback_url = "http://localhost:3000"  # ← update to your frontend URL in production
    client_class = OAuth2Client

    @extend_schema(
        tags=["Social Auth"],
        summary="Login with Google",
        description=(
            "Exchange a **Google OAuth2 access token** for JWT tokens.\n\n"
            "### Frontend integration steps:\n"
            "1. Add the Google Identity SDK to your frontend\n"
            "2. User clicks **Sign in with Google**\n"
            "3. Google returns an `access_token` to your frontend\n"
            "4. POST that `access_token` to this endpoint\n"
            "5. Store the returned JWT `access` and `refresh` tokens\n\n"
            "### Google Cloud Console setup:\n"
            "**Authorised JavaScript Origins:**\n"
            "```\n"
            "http://localhost:3000\n"
            "https://yourfrontend.onrender.com\n"
            "```\n"
            "**Authorised Redirect URIs:**\n"
            "```\n"
            "http://localhost:8000/api/auth/google/\n"
            "https://yourbackend.onrender.com/api/auth/google/\n"
            "```\n\n"
            "New accounts are **created automatically**. "
            "Google-authenticated users are **pre-verified** (no OTP needed)."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["access_token"],
                "properties": {
                    "access_token": {
                        "type": "string",
                        "description": "The OAuth2 access token received from Google",
                        "example": "ya29.a0AfH6SMBx_your_google_token_here",
                    }
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="Google login successful. JWT access + refresh tokens returned."
            ),
            400: OpenApiResponse(
                description="Invalid or expired Google access token."
            ),
        },
        examples=[
            OpenApiExample(
                "Google token exchange",
                value={"access_token": "ya29.a0AfH6SMBx_your_google_token_here"},
                request_only=True,
            )
        ],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)