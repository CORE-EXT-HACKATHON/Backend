import factory
from faker import Faker
from django.contrib.auth import get_user_model
from django.utils import timezone
from accounts.models import OTPCode

fake = Faker()
User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.LazyAttribute(lambda _: fake.unique.email())
    first_name = factory.LazyAttribute(lambda _: fake.first_name())
    last_name = factory.LazyAttribute(lambda _: fake.last_name())
    password = factory.PostGenerationMethodCall('set_password', 'TestPass123!')
    is_active = True
    is_verified = True


class UnverifiedUserFactory(UserFactory):
    is_verified = False


class OTPFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OTPCode

    user = factory.SubFactory(UserFactory)
    code = '1234'
    otp_type = 'verify_email'
    is_used = False
    expires_at = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(minutes=10)
    )


class ExpiredOTPFactory(OTPFactory):
    expires_at = factory.LazyFunction(
        lambda: timezone.now() - timezone.timedelta(minutes=1)
    )


class UsedOTPFactory(OTPFactory):
    is_used = True