import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock
from accounts.models import OTPCode
from .factories import (
    UserFactory,
    UnverifiedUserFactory,
    OTPFactory,
    ExpiredOTPFactory,
    UsedOTPFactory,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def verified_user():
    return UserFactory()


@pytest.fixture
def unverified_user():
    return UnverifiedUserFactory()


@pytest.fixture
def auth_client(verified_user):
    client = APIClient()
    response = client.post(reverse('login'), {
        'email': verified_user.email,
        'password': 'TestPass123!',
    }, format='json')
    token = response.data['access']
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client, verified_user


# ─── Register Tests ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRegister:
    url = '/api/auth/register/'

    @patch('accounts.views.send_otp_email')
    def test_register_success(self, mock_email, client):
        response = client.post(self.url, {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }, format='json')

        assert response.status_code == 201
        assert 'email' in response.data
        assert mock_email.called
        assert OTPCode.objects.filter(otp_type='verify_email').exists()

    @patch('accounts.views.send_otp_email')
    def test_register_duplicate_verified_email(self, mock_email, client, verified_user):
        response = client.post(self.url, {
            'first_name': 'Jane',
            'last_name': 'Doe',
            'email': verified_user.email,
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }, format='json')

        assert response.status_code == 400
        assert 'email' in response.data

    def test_register_password_mismatch(self, client):
        response = client.post(self.url, {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'new@example.com',
            'password': 'StrongPass123!',
            'confirm_password': 'WrongPass123!',
        }, format='json')

        assert response.status_code == 400

    def test_register_missing_fields(self, client):
        response = client.post(self.url, {
            'email': 'john@example.com',
        }, format='json')

        assert response.status_code == 400

    def test_register_invalid_email(self, client):
        response = client.post(self.url, {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'not-an-email',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }, format='json')

        assert response.status_code == 400

    def test_register_weak_password(self, client):
        response = client.post(self.url, {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'password': '123',
            'confirm_password': '123',
        }, format='json')

        assert response.status_code == 400


# ─── Verify Email Tests ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestVerifyEmail:
    url = '/api/auth/verify-email/'

    def test_verify_email_success(self, client, unverified_user):
        otp = OTPFactory(user=unverified_user, otp_type='verify_email')

        response = client.post(self.url, {
            'email': unverified_user.email,
            'code': otp.code,
        }, format='json')

        assert response.status_code == 200
        assert 'access' in response.data
        assert 'refresh' in response.data

        unverified_user.refresh_from_db()
        assert unverified_user.is_verified is True

        otp.refresh_from_db()
        assert otp.is_used is True

    def test_verify_email_wrong_code(self, client, unverified_user):
        OTPFactory(user=unverified_user, otp_type='verify_email', code='1234')

        response = client.post(self.url, {
            'email': unverified_user.email,
            'code': '9999',
        }, format='json')

        assert response.status_code == 400
        assert 'code' in response.data

    def test_verify_email_expired_otp(self, client, unverified_user):
        otp = ExpiredOTPFactory(user=unverified_user, otp_type='verify_email')

        response = client.post(self.url, {
            'email': unverified_user.email,
            'code': otp.code,
        }, format='json')

        assert response.status_code == 400

    def test_verify_email_used_otp(self, client, unverified_user):
        otp = UsedOTPFactory(user=unverified_user, otp_type='verify_email')

        response = client.post(self.url, {
            'email': unverified_user.email,
            'code': otp.code,
        }, format='json')

        assert response.status_code == 400

    def test_verify_email_nonexistent_user(self, client):
        response = client.post(self.url, {
            'email': 'nobody@example.com',
            'code': '1234',
        }, format='json')

        assert response.status_code == 400


# ─── Login Tests ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLogin:
    url = '/api/auth/login/'

    def test_login_success(self, client, verified_user):
        response = client.post(self.url, {
            'email': verified_user.email,
            'password': 'TestPass123!',
        }, format='json')

        assert response.status_code == 200
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert 'user' in response.data

    def test_login_wrong_password(self, client, verified_user):
        response = client.post(self.url, {
            'email': verified_user.email,
            'password': 'WrongPassword!',
        }, format='json')

        assert response.status_code == 400

    def test_login_wrong_email(self, client):
        response = client.post(self.url, {
            'email': 'nobody@example.com',
            'password': 'TestPass123!',
        }, format='json')

        assert response.status_code == 400

    def test_login_unverified_user(self, client, unverified_user):
        response = client.post(self.url, {
            'email': unverified_user.email,
            'password': 'TestPass123!',
        }, format='json')

        assert response.status_code == 400
        assert 'email' in response.data

    def test_login_missing_fields(self, client):
        response = client.post(self.url, {
            'email': 'john@example.com',
        }, format='json')

        assert response.status_code == 400


# ─── Forgot Password Tests ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestForgotPassword:
    url = '/api/auth/forgot-password/'

    @patch('accounts.views.send_otp_email')
    def test_forgot_password_existing_email(self, mock_email, client, verified_user):
        response = client.post(self.url, {
            'email': verified_user.email,
        }, format='json')

        assert response.status_code == 200
        assert mock_email.called
        assert OTPCode.objects.filter(
            user=verified_user,
            otp_type='reset_password'
        ).exists()

    @patch('accounts.views.send_otp_email')
    def test_forgot_password_nonexistent_email(self, mock_email, client):
        # Should still return 200 to prevent email enumeration
        response = client.post(self.url, {
            'email': 'nobody@example.com',
        }, format='json')

        assert response.status_code == 200
        assert not mock_email.called

    @patch('accounts.views.send_otp_email')
    def test_forgot_password_unverified_user(self, mock_email, client, unverified_user):
        # Unverified users should not receive reset OTP
        response = client.post(self.url, {
            'email': unverified_user.email,
        }, format='json')

        assert response.status_code == 200
        assert not mock_email.called


# ─── Reset Password Tests ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestResetPassword:
    url = '/api/auth/reset-password/'

    def test_reset_password_success(self, client, verified_user):
        otp = OTPFactory(user=verified_user, otp_type='reset_password')

        response = client.post(self.url, {
            'email': verified_user.email,
            'code': otp.code,
            'new_password': 'NewStrongPass123!',
            'confirm_password': 'NewStrongPass123!',
        }, format='json')

        assert response.status_code == 200

        # Verify password actually changed
        verified_user.refresh_from_db()
        assert verified_user.check_password('NewStrongPass123!')

        # Verify OTP marked as used
        otp.refresh_from_db()
        assert otp.is_used is True

    def test_reset_password_wrong_code(self, client, verified_user):
        OTPFactory(user=verified_user, otp_type='reset_password', code='1234')

        response = client.post(self.url, {
            'email': verified_user.email,
            'code': '9999',
            'new_password': 'NewStrongPass123!',
            'confirm_password': 'NewStrongPass123!',
        }, format='json')

        assert response.status_code == 400

    def test_reset_password_expired_otp(self, client, verified_user):
        otp = ExpiredOTPFactory(user=verified_user, otp_type='reset_password')

        response = client.post(self.url, {
            'email': verified_user.email,
            'code': otp.code,
            'new_password': 'NewStrongPass123!',
            'confirm_password': 'NewStrongPass123!',
        }, format='json')

        assert response.status_code == 400

    def test_reset_password_mismatch(self, client, verified_user):
        otp = OTPFactory(user=verified_user, otp_type='reset_password')

        response = client.post(self.url, {
            'email': verified_user.email,
            'code': otp.code,
            'new_password': 'NewStrongPass123!',
            'confirm_password': 'DifferentPass123!',
        }, format='json')

        assert response.status_code == 400

    def test_reset_password_otp_single_use(self, client, verified_user):
        otp = OTPFactory(user=verified_user, otp_type='reset_password')

        # Use the OTP successfully
        client.post(self.url, {
            'email': verified_user.email,
            'code': otp.code,
            'new_password': 'NewStrongPass123!',
            'confirm_password': 'NewStrongPass123!',
        }, format='json')

        # Try to use the same OTP again
        response = client.post(self.url, {
            'email': verified_user.email,
            'code': otp.code,
            'new_password': 'AnotherPass123!',
            'confirm_password': 'AnotherPass123!',
        }, format='json')

        assert response.status_code == 400


# ─── Resend OTP Tests ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestResendOTP:
    url = '/api/auth/resend-otp/'

    @patch('accounts.views.send_otp_email')
    def test_resend_verify_email_otp(self, mock_email, client, unverified_user):
        response = client.post(self.url, {
            'email': unverified_user.email,
            'otp_type': 'verify_email',
        }, format='json')

        assert response.status_code == 200
        assert mock_email.called
        assert OTPCode.objects.filter(
            user=unverified_user,
            otp_type='verify_email',
            is_used=False
        ).exists()

    @patch('accounts.views.send_otp_email')
    def test_resend_reset_password_otp(self, mock_email, client, verified_user):
        response = client.post(self.url, {
            'email': verified_user.email,
            'otp_type': 'reset_password',
        }, format='json')

        assert response.status_code == 200
        assert mock_email.called

    @patch('accounts.views.send_otp_email')
    def test_resend_invalidates_old_otp(self, mock_email, client, unverified_user):
        old_otp = OTPFactory(user=unverified_user, otp_type='verify_email', code='1111')

        client.post(self.url, {
            'email': unverified_user.email,
            'otp_type': 'verify_email',
        }, format='json')

        # Old OTP should be deleted
        assert not OTPCode.objects.filter(id=old_otp.id).exists()

    def test_resend_nonexistent_email(self, client):
        response = client.post(self.url, {
            'email': 'nobody@example.com',
            'otp_type': 'verify_email',
        }, format='json')

        assert response.status_code == 400

    def test_resend_invalid_otp_type(self, client, verified_user):
        response = client.post(self.url, {
            'email': verified_user.email,
            'otp_type': 'invalid_type',
        }, format='json')

        assert response.status_code == 400


# ─── Profile Tests ────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProfile:
    url = '/api/auth/profile/'

    def test_get_profile_authenticated(self, auth_client):
        client, user = auth_client
        response = client.get(self.url)

        assert response.status_code == 200
        assert response.data['email'] == user.email
        assert response.data['first_name'] == user.first_name

    def test_get_profile_unauthenticated(self, client):
        response = client.get(self.url)
        assert response.status_code == 401

    def test_update_profile_success(self, auth_client):
        client, user = auth_client
        response = client.patch(self.url, {
            'first_name': 'UpdatedName',
            'last_name': 'UpdatedLast',
        }, format='json')

        assert response.status_code == 200
        assert response.data['first_name'] == 'UpdatedName'
        assert response.data['last_name'] == 'UpdatedLast'

        user.refresh_from_db()
        assert user.first_name == 'UpdatedName'

    def test_update_profile_unauthenticated(self, client):
        response = client.patch(self.url, {
            'first_name': 'UpdatedName',
        }, format='json')

        assert response.status_code == 401

    def test_cannot_update_email_via_profile(self, auth_client):
        client, user = auth_client
        original_email = user.email

        response = client.patch(self.url, {
            'email': 'newemail@example.com',
        }, format='json')

        user.refresh_from_db()
        assert user.email == original_email


# ─── Change Password Tests ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestChangePassword:
    url = '/api/auth/change-password/'

    def test_change_password_success(self, auth_client):
        client, user = auth_client
        response = client.post(self.url, {
            'old_password': 'TestPass123!',
            'new_password': 'NewStrongPass456!',
            'confirm_password': 'NewStrongPass456!',
        }, format='json')

        assert response.status_code == 200

        user.refresh_from_db()
        assert user.check_password('NewStrongPass456!')

    def test_change_password_wrong_old_password(self, auth_client):
        client, user = auth_client
        response = client.post(self.url, {
            'old_password': 'WrongOldPass!',
            'new_password': 'NewStrongPass456!',
            'confirm_password': 'NewStrongPass456!',
        }, format='json')

        assert response.status_code == 400

    def test_change_password_mismatch(self, auth_client):
        client, user = auth_client
        response = client.post(self.url, {
            'old_password': 'TestPass123!',
            'new_password': 'NewStrongPass456!',
            'confirm_password': 'DifferentPass456!',
        }, format='json')

        assert response.status_code == 400

    def test_change_password_unauthenticated(self, client):
        response = client.post(self.url, {
            'old_password': 'TestPass123!',
            'new_password': 'NewStrongPass456!',
            'confirm_password': 'NewStrongPass456!',
        }, format='json')

        assert response.status_code == 401


# ─── Token Refresh Tests ──────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTokenRefresh:
    url = '/api/auth/token/refresh/'

    def test_token_refresh_success(self, client, verified_user):
        login_response = client.post('/api/auth/login/', {
            'email': verified_user.email,
            'password': 'TestPass123!',
        }, format='json')

        refresh_token = login_response.data['refresh']
        response = client.post(self.url, {
            'refresh': refresh_token,
        }, format='json')

        assert response.status_code == 200
        assert 'access' in response.data

    def test_token_refresh_invalid_token(self, client):
        response = client.post(self.url, {
            'refresh': 'invalidtoken123',
        }, format='json')

        assert response.status_code == 401


# ─── OTP Model Tests ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestOTPModel:

    def test_otp_is_valid(self, verified_user):
        otp = OTPFactory(user=verified_user)
        assert otp.is_valid() is True

    def test_otp_expired_is_invalid(self, verified_user):
        otp = ExpiredOTPFactory(user=verified_user)
        assert otp.is_valid() is False

    def test_otp_used_is_invalid(self, verified_user):
        otp = UsedOTPFactory(user=verified_user)
        assert otp.is_valid() is False

    def test_generate_otp_invalidates_previous(self, verified_user):
        old_otp = OTPFactory(user=verified_user, otp_type='verify_email')
        OTPCode.generate_otp(verified_user, 'verify_email')

        assert not OTPCode.objects.filter(id=old_otp.id).exists()

    def test_generate_otp_is_4_digits(self, verified_user):
        otp = OTPCode.generate_otp(verified_user, 'verify_email')
        assert len(otp.code) == 4
        assert otp.code.isdigit()

    def test_generate_otp_expires_in_10_minutes(self, verified_user):
        otp = OTPCode.generate_otp(verified_user, 'verify_email')
        diff = otp.expires_at - timezone.now()
        assert 9 * 60 < diff.seconds <= 10 * 60