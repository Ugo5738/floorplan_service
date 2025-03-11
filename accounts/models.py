import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField

from helpers.models import TrackingModel

GENDER_CHOICES = (("M", "Male"), ("F", "Female"))


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users require an email field")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser, TrackingModel):
    email = models.EmailField(
        _("email address"), db_index=True, blank=True, null=True, unique=True
    )
    username = models.CharField(
        _("username"), max_length=30, blank=True, null=True, unique=False
    )
    phone = models.CharField(max_length=60, blank=True, null=True)
    gender = models.CharField(
        max_length=1, choices=GENDER_CHOICES, blank=True, null=True
    )
    date_of_birth = models.DateField(null=True, blank=True)
    profile_picture = models.ImageField(
        upload_to="profile_pics/", null=True, blank=True
    )

    email_verification_token = models.CharField(max_length=128, null=True, blank=True)
    email_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text="Designates whether this users email is verified.",
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return "{}".format(self.email)

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")


class OrganizationProfile(TrackingModel):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="organization_profile"
    )
    name = models.CharField(max_length=100)
    bio = models.TextField(max_length=500, blank=True, null=True)

    # organization address
    city = models.CharField(max_length=50, blank=True, null=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    address2 = models.CharField(max_length=255, null=True, blank=True)
    country = CountryField(multiple=False, null=True, blank=True)
    zip_code = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return "{}".format(self.name)

    class Meta:
        verbose_name = _("Organization")
        verbose_name_plural = _("Organizations")


class UserToken(models.Model):
    phone_number = models.CharField(max_length=20)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
