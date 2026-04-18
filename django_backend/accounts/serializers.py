from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import OTPCode

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password', 'confirm_password']

    def validate_email(self, email):
        if User.objects.filter(email=email, is_verified=True).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        # If unverified account exists, update it
        user, _ = User.objects.update_or_create(
            email=validated_data['email'],
            defaults={
                'first_name': validated_data['first_name'],
                'last_name': validated_data['last_name'],
                'is_verified': False,
                'is_active': True,
            }
        )
        user.set_password(validated_data['password'])
        user.save()
        return user


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=4, min_length=4)

    def validate(self, data):
        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "No account found with this email."})

        try:
            otp = OTPCode.objects.get(
                user=user,
                code=data['code'],
                otp_type='verify_email',
                is_used=False
            )
        except OTPCode.DoesNotExist:
            raise serializers.ValidationError({"code": "Invalid OTP code."})

        if not otp.is_valid():
            raise serializers.ValidationError({"code": "This OTP has expired. Please request a new one."})

        data['user'] = user
        data['otp'] = otp
        return data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email or password."})

        if not user.check_password(data['password']):
            raise serializers.ValidationError({"password": "Invalid email or password."})

        if not user.is_verified:
            raise serializers.ValidationError({"email": "Please verify your email first."})

        if not user.is_active:
            raise serializers.ValidationError({"email": "Your account has been deactivated."})

        data['user'] = user
        return data


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, email):
        try:
            user = User.objects.get(email=email, is_verified=True)
            self.context['user'] = user
        except User.DoesNotExist:
            # Don't reveal if email exists — just silently pass
            self.context['user'] = None
        return email


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=4, min_length=4)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "No account found with this email."})

        try:
            otp = OTPCode.objects.get(
                user=user,
                code=data['code'],
                otp_type='reset_password',
                is_used=False
            )
        except OTPCode.DoesNotExist:
            raise serializers.ValidationError({"code": "Invalid OTP code."})

        if not otp.is_valid():
            raise serializers.ValidationError({"code": "This OTP has expired. Please request a new one."})

        data['user'] = user
        data['otp'] = otp
        return data


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_type = serializers.ChoiceField(choices=['verify_email', 'reset_password'])

    def validate_email(self, email):
        try:
            User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("No account found with this email.")
        return email


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'avatar', 'is_verified', 'date_joined']
        read_only_fields = ['id', 'email', 'is_verified', 'date_joined']