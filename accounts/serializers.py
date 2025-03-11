from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts import models


class OrganizationProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.OrganizationProfile
        # fields = '__all__'
        fields = ["name", "country"]  # added to registration form


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    country = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = models.User
        fields = ["email", "password", "country", "first_name", "last_name"]
        extra_kwargs = {
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    def create(self, validated_data):
        country = validated_data.pop("country", None)
        user = models.User.objects.create_user(**validated_data)
        if country:
            models.OrganizationProfile.objects.create(user=user, country=country)
        return user


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    user_role = serializers.CharField(source="get_user_role", read_only=True)

    class Meta:
        model = models.User
        # fields = '__all__'
        exclude = ["password", "groups", "user_permissions"]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change endpoint.
    """

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class ResetPasswordRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
