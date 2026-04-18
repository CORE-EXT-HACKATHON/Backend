from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth import get_user_model
from django.utils.decorators import method_decorator

from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
)

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialToken, SocialApp
from django.contrib.auth import get_user_model
import requests as http_requests

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


def ratelimited_error(request, exception):
    """Custom handler for rate limit breaches (wire into urls.py if needed)."""
    return Response(
        {"error": "Too many requests. Please wait before trying again."},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


# ─── Register ─────────────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="5/h", method="POST", block=True),
    name="post",
)
class RegisterView(APIView):
    """
    Register a new user account.
    Rate limited to 5 requests per hour per IP.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Register a new user",
        description=(
            "Creates a new user account and sends a **4-digit OTP** to the "
            "provided email address for verification.\n\n"
            "- Rate limited: **5 requests/hour per IP**\n"
            "- OTP expires in **10 minutes**\n"
            "- Account is inactive until email is verified"
        ),
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(description="Account created — OTP sent to email"),
            400: OpenApiResponse(description="Validation errors (e.g. email taken, passwords mismatch)"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        examples=[
            OpenApiExample(
                "Register Example",
                value={
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john@example.com",
                    "password": "StrongPass123!",
                    "confirm_password": "StrongPass123!",
                },
            )
        ],
    )
    def post(self, request):
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
    ratelimit(key="ip", rate="10/h", method="POST", block=True),
    name="post",
)
class VerifyEmailView(APIView):
    """
    Verify a user's email using the 4-digit OTP.
    Rate limited to 10 attempts per hour per IP (prevents brute force).
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["OTP"],
        summary="Verify email with OTP",
        description=(
            "Verifies the **4-digit OTP** sent to the user's email during registration.\n\n"
            "On success, the account is activated and **JWT tokens are returned** "
            "so the user is logged in immediately.\n\n"
            "- Rate limited: **10 attempts/hour per IP**\n"
            "- OTP is single-use and expires after **10 minutes**"
        ),
        request=VerifyEmailSerializer,
        responses={
            200: OpenApiResponse(description="Email verified — JWT tokens returned"),
            400: OpenApiResponse(description="Invalid or expired OTP"),
            429: OpenApiResponse(description="Rate limit exceeded — too many attempts"),
        },
        examples=[
            OpenApiExample(
                "Verify OTP Example",
                value={"email": "john@example.com", "code": "4821"},
            )
        ],
    )
    def post(self, request):
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
    ratelimit(key="ip", rate="10/h", method="POST", block=True),
    name="post",
)
class LoginView(APIView):
    """
    Authenticate a verified user and return JWT tokens.
    Rate limited to 10 requests per hour per IP.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="Login",
        description=(
            "Authenticates a verified user and returns **JWT access + refresh tokens**.\n\n"
            "- The `access` token expires in **60 minutes**\n"
            "- The `refresh` token expires in **7 days**\n"
            "- Use `POST /api/auth/token/refresh/` to get a new access token\n"
            "- Rate limited: **10 requests/hour per IP**"
        ),
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Login successful — JWT tokens returned"),
            400: OpenApiResponse(description="Invalid credentials or unverified email"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        examples=[
            OpenApiExample(
                "Login Example",
                value={"email": "john@example.com", "password": "StrongPass123!"},
            )
        ],
    )
    def post(self, request):
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
    ratelimit(key="ip", rate="5/h", method="POST", block=True),
    name="post",
)
class ForgotPasswordView(APIView):
    """
    Request a password reset OTP.
    Always returns 200 to prevent email enumeration attacks.
    Rate limited to 5 requests per hour per IP.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Password"],
        summary="Forgot password — request OTP",
        description=(
            "Sends a **4-digit OTP** to the email address for password reset.\n\n"
            "**Always returns HTTP 200** regardless of whether the email exists — "
            "this prevents attackers from discovering registered emails.\n\n"
            "- Rate limited: **5 requests/hour per IP**\n"
            "- OTP expires in **10 minutes**"
        ),
        request=ForgotPasswordSerializer,
        responses={
            200: OpenApiResponse(description="OTP sent if account exists (always 200)"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        examples=[
            OpenApiExample(
                "Forgot Password Example",
                value={"email": "john@example.com"},
            )
        ],
    )
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data, context={})
        if serializer.is_valid():
            user = serializer.context.get("user")
            if user:
                otp = OTPCode.generate_otp(user, "reset_password")
                send_otp_email(user, otp.code, "reset_password")
        # Always return same response — never reveal if email is registered
        return Response(
            {"message": "If an account with that email exists, a reset OTP has been sent."}
        )


# ─── Reset Password ───────────────────────────────────────────────────────────

@method_decorator(
    ratelimit(key="ip", rate="10/h", method="POST", block=True),
    name="post",
)
class ResetPasswordView(APIView):
    """
    Reset password using OTP.
    Rate limited to 10 attempts per hour per IP.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Password"],
        summary="Reset password with OTP",
        description=(
            "Verifies the **4-digit OTP** and sets a new password.\n\n"
            "- OTP must not be expired or already used\n"
            "- New password must meet Django's password validation rules\n"
            "- Rate limited: **10 attempts/hour per IP**"
        ),
        request=ResetPasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successful"),
            400: OpenApiResponse(description="Invalid/expired OTP or passwords do not match"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        examples=[
            OpenApiExample(
                "Reset Password Example",
                value={
                    "email": "john@example.com",
                    "code": "3847",
                    "new_password": "NewStrongPass456!",
                    "confirm_password": "NewStrongPass456!",
                },
            )
        ],
    )
    def post(self, request):
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
    ratelimit(key="ip", rate="3/h", method="POST", block=True),
    name="post",
)
class ResendOTPView(APIView):
    """
    Resend a fresh OTP code.
    Strictest rate limit — 3 per hour per IP — to prevent OTP spam/flooding.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["OTP"],
        summary="Resend OTP",
        description=(
            "Cancels any existing unused OTP and sends a fresh **4-digit OTP**.\n\n"
            "Use `otp_type`:\n"
            "- `verify_email` — for registration verification\n"
            "- `reset_password` — for password reset\n\n"
            "- Rate limited: **3 requests/hour per IP** (strictest limit to prevent spam)\n"
            "- New OTP expires in **10 minutes**"
        ),
        request=ResendOTPSerializer,
        responses={
            200: OpenApiResponse(description="New OTP sent successfully"),
            400: OpenApiResponse(description="Invalid email or otp_type"),
            429: OpenApiResponse(description="Rate limit exceeded — max 3/hour"),
        },
        examples=[
            OpenApiExample(
                "Resend for email verification",
                value={"email": "john@example.com", "otp_type": "verify_email"},
            ),
            OpenApiExample(
                "Resend for password reset",
                value={"email": "john@example.com", "otp_type": "reset_password"},
            ),
        ],
    )
    def post(self, request):
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
    """
    Get or update the authenticated user's profile.
    Requires a valid JWT Bearer token.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Profile"],
        summary="Get my profile",
        description=(
            "Returns the currently authenticated user's profile data.\n\n"
            "**Requires:** `Authorization: Bearer <access_token>`"
        ),
        responses={
            200: UserSerializer,
            401: OpenApiResponse(description="Not authenticated"),
        },
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        tags=["Profile"],
        summary="Update my profile",
        description=(
            "Partially updates the authenticated user's profile.\n\n"
            "All fields are optional — only send what you want to change.\n\n"
            "**Requires:** `Authorization: Bearer <access_token>`"
        ),
        request=UserSerializer,
        responses={
            200: UserSerializer,
            400: OpenApiResponse(description="Validation errors"),
            401: OpenApiResponse(description="Not authenticated"),
        },
        examples=[
            OpenApiExample(
                "Update name",
                value={"first_name": "Jane", "last_name": "Smith"},
            )
        ],
    )
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Change Password ──────────────────────────────────────────────────────────

class ChangePasswordView(APIView):
    """
    Change password for an authenticated user.
    Requires a valid JWT Bearer token.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Password"],
        summary="Change password",
        description=(
            "Changes the password for the currently authenticated user.\n\n"
            "- Requires the current (old) password for verification\n"
            "- New password must meet Django's password validation rules\n\n"
            "**Requires:** `Authorization: Bearer <access_token>`"
        ),
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password changed successfully"),
            400: OpenApiResponse(description="Old password incorrect or new passwords do not match"),
            401: OpenApiResponse(description="Not authenticated"),
        },
        examples=[
            OpenApiExample(
                "Change Password Example",
                value={
                    "old_password": "OldPass123!",
                    "new_password": "NewPass456!",
                    "confirm_password": "NewPass456!",
                },
            )
        ],
    )
    def post(self, request):
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

class GoogleLogin(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Social Auth"],
        summary="Login with Google",
        description=(
            "Exchange a **Google OAuth2 access token** for JWT tokens.\n\n"
            "### Steps:\n"
            "1. User signs in with Google on your frontend\n"
            "2. Google returns an `access_token`\n"
            "3. POST that token here\n"
            "4. Receive JWT access + refresh tokens\n\n"
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
            "New accounts are created automatically and pre-verified."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["access_token"],
                "properties": {
                    "access_token": {
                        "type": "string",
                        "example": "ya29.a0AfH6SMBx_your_google_token_here",
                    }
                },
            }
        },
        responses={
            200: OpenApiResponse(description="JWT tokens returned."),
            400: OpenApiResponse(description="Invalid or expired Google access token."),
        },
        examples=[
            OpenApiExample(
                "Google token exchange",
                value={"access_token": "ya29.a0AfH6SMBx_your_google_token_here"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        access_token = request.data.get("access_token")
        if not access_token:
            return Response(
                {"error": "access_token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify token and get user info from Google
        google_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        response = http_requests.get(
            google_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

        if response.status_code != 200:
            return Response(
                {"error": "Invalid or expired Google access token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        google_data = response.json()
        email = google_data.get("email")
        first_name = google_data.get("given_name", "")
        last_name = google_data.get("family_name", "")

        if not email:
            return Response(
                {"error": "Could not retrieve email from Google."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get or create user
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "is_verified": True,  # Google users are pre-verified
                "is_active": True,
            },
        )

        # If user existed but wasn't verified, verify them now
        if not created and not user.is_verified:
            user.is_verified = True
            user.save()

        tokens = get_tokens_for_user(user)
        return Response(
            {
                "message": "Google login successful!",
                "user": UserSerializer(user).data,
                **tokens,
            }
        )
    """
    Login or register via Google OAuth.
    Accepts a Google access token and returns JWT tokens.
    """

    adapter_class = GoogleOAuth2Adapter
    callback_url = "http://localhost:3000"   # ← update to your frontend URL in production
    client_class = OAuth2Client

    @extend_schema(
        tags=["Social Auth"],
        summary="Login with Google",
        description=(
            "Exchange a **Google OAuth access token** for JWT tokens.\n\n"
            "### Frontend flow\n"
            "1. Load the [Google Identity SDK](https://developers.google.com/identity) on your frontend\n"
            "2. User clicks **Login with Google** → Google returns an `access_token`\n"
            "3. POST that token to this endpoint\n"
            "4. Receive `access` + `refresh` JWT tokens — user is now logged in\n\n"
            "### Google Cloud Console setup\n"
            "- **Authorised JavaScript Origins:** `http://localhost:3000`, `https://yourapp.com`\n"
            "- **Authorised Redirect URIs:** `http://localhost:8000/api/auth/google/`, `https://yourbackend.com/api/auth/google/`\n\n"
            "### Notes\n"
            "- If the Google email is new, an account is **automatically created**\n"
            "- If the email already exists, the accounts are **linked**\n"
            "- Google-authenticated users skip OTP verification"
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["access_token"],
                "properties": {
                    "access_token": {
                        "type": "string",
                        "description": "The access_token returned by Google's OAuth flow",
                        "example": "ya29.a0AfH6SMBx...",
                    }
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="Google auth successful — JWT tokens returned",
            ),
            400: OpenApiResponse(description="Invalid or expired Google token"),
        },
        examples=[
            OpenApiExample(
                "Google Login Example",
                value={"access_token": "ya29.a0AfH6SMBx_your_google_token_here"},
            )
        ],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)