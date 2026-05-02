from rest_framework.throttling import AnonRateThrottle

class RegisterThrottle(AnonRateThrottle):
    scope = 'register'

class VerifyOTPThrottle(AnonRateThrottle):
    scope = 'verify_otp'

class LoginThrottle(AnonRateThrottle):
    scope = 'login'

class ForgotPasswordThrottle(AnonRateThrottle):
    scope = 'forgot_password'

class ResetPasswordThrottle(AnonRateThrottle):
    scope = 'reset_password'

class ResendOTPThrottle(AnonRateThrottle):
    scope = 'resend_otp'

class ChangePasswordThrottle(AnonRateThrottle):
    scope = 'change_password'