import uuid
from datetime import timedelta
from typing import Any

import jwt
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.core.mail import send_mail
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, status, viewsets
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from accounts.models import User, UserToken
from accounts.pagination import CustomPageNumberPagination
from accounts.serializers import (
    ChangePasswordSerializer,
    RegisterSerializer,
    UserSerializer,
)

# from utils.email_utils import send_verification_email


@method_decorator(ensure_csrf_cookie, name="dispatch")
class GetCSRFToken(APIView):
    def get(self, request):
        csrf_token = get_token(request)
        return JsonResponse({"success": "CSRF cookie set", "csrftoken": csrf_token})


class GenerateTokenView(APIView):
    """
    Generate authentication token for phone number.

    This endpoint generates a new token or retrieves an existing one for the provided phone number.
    """

    def post(self, request):
        """
        Generate token for authentication.

        Parameters:
            phone_number (str): User's phone number

        Returns:
            token (str): Generated authentication token

        Raises:
            400: If phone number is not provided
        """
        phone_number = request.data.get("phone_number")
        if not phone_number:
            return Response(
                {"error": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_token, created = UserToken.objects.get_or_create(phone_number=phone_number)
        return Response({"token": str(user_token.token)}, status=status.HTTP_200_OK)


class TokenAuthenticationView(APIView):
    """
    Authenticate user using generated token.

    This endpoint validates the token and returns JWT tokens for further authentication.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        """
        Authenticate using token.

        Parameters:
            token (str): Authentication token previously generated

        Returns:
            refresh (str): JWT refresh token
            access (str): JWT access token
            message (str): Success message
            user (dict): User details including id and phone

        Raises:
            400: If token is invalid or not provided
        """
        token = request.data.get("token")
        if not token:
            return Response(
                {"error": "Token is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user_token = UserToken.objects.get(token=token)

            # Get or create the user
            user, created = User.objects.get_or_create(phone=user_token.phone_number)

            # Generate JWT tokens with additional claims
            refresh = RefreshToken.for_user(user)
            refresh["phone"] = user.phone  # Add phone number to token claims
            refresh["user_id"] = user.id  # Add the user_id claim
            access_token = str(refresh.access_token)

            return Response(
                {
                    "refresh": str(refresh),
                    "access": access_token,
                    "message": "Authenticated successfully.",
                    "user": {"id": user.id, "phone": user.phone},
                },
                status=status.HTTP_200_OK,
            )
        except UserToken.DoesNotExist:
            return Response(
                {"error": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST
            )


class PhoneAuthenticationView(APIView):
    def post(self, request):
        phone_number = request.data.get("phone_number")
        if not phone_number:
            return Response(
                {"error": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Best practice, send an OTP here
        # For now, we'll authenticate directly (Note: This is not secure)
        user, created = User.objects.get_or_create(phone=phone_number)

        # Generate JWT tokens with additional claims
        refresh = RefreshToken.for_user(user)
        refresh["phone"] = user.phone  # Add phone number to token claims
        access_token = str(refresh.access_token)

        return Response(
            {
                "refresh": str(refresh),
                "access": access_token,
                "message": "Authenticated successfully.",
                "user": {"id": user.id, "phone": user.phone},
            },
            status=status.HTTP_200_OK,
        )


class CheckAuthenticatedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        print("This is the user: ", request.user.phone)
        return Response({"message": "Authenticated"}, status=status.HTTP_200_OK)


# class RegisterAPIView(GenericAPIView):
#     """
#     API endpoint that allows users to be created.

#     Expected payload:
#     {
#         "password": "password",
#         "first_name": "John",
#         "last_name": "Doe",
#         "email": "johndoe@example.com",
#         "country": "NG"
#     }
#     """
#     permission_classes = [AllowAny]
#     authentication_classes = []
#     serializer_class = RegisterSerializer

#     def post(self, request: Request) -> Response:
#         serializer = self.serializer_class(data=request.data)

#         if serializer.is_valid():
#             user = serializer.save()
#             user.email_verified = False  # Set email_verified to False initially
#             user.email_verification_token = get_random_string(64)
#             user.save()

#             # Send verification email
#             verification_link = f"{settings.FRONTEND_BASE_URL}/verify-email/{user.email_verification_token}"
#             email_response = send_verification_email(user.email, verification_link)

#             if email_response.status_code == 200:
#                 return Response({
#                     "message": "User registered successfully. Please check your email to verify your account.",
#                     "user_id": user.id
#                 }, status=status.HTTP_201_CREATED)
#             else:
#                 return Response({
#                     "message": "User registered successfully, but there was an issue sending the verification email. Please try again later.",
#                     "user_id": user.id
#                 }, status=status.HTTP_201_CREATED)
#         else:
#             print("Data not valid")
#             errors = {}
#             for field, field_errors in serializer.errors.items():
#                 errors[field] = field_errors[0]  # Take the first error message for each field

#             if 'email' in errors and 'unique' in errors['email'].lower():
#                 errors['email'] = "A user with this email already exists."

#             if 'password' in errors:
#                 if 'too short' in errors['password'].lower():
#                     errors['password'] = "Password is too short. It must be at least 8 characters long."
#                 elif 'too common' in errors['password'].lower():
#                     errors['password'] = "This password is too common. Please choose a more unique password."
#                 elif 'entirely numeric' in errors['password'].lower():
#                     errors['password'] = "Password cannot be entirely numeric."

#             return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)


# class VerifyEmailView(APIView):
#     def get(self, request, token):
#         try:
#             user = User.objects.get(email_verification_token=token)
#             user.email_verified = True
#             # user.email_verification_token = ''
#             user.save()
#             return Response({"message": "Email verified successfully"}, status=status.HTTP_200_OK)
#         except User.DoesNotExist:
#             return Response({"message": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)


# class ResendVerificationEmailView(APIView):
#     def post(self, request):
#         email = request.data.get('email')
#         if not email:
#             return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             user = User.objects.get(email=email)
#             if user.email_verified:
#                 return Response({"message": "Email is already verified"}, status=status.HTTP_400_BAD_REQUEST)

#             user.email_verification_token = get_random_string(64)
#             user.save()

#             verification_link = f"{settings.FRONTEND_BASE_URL}/verify-email/{user.email_verification_token}"
#             email_response = send_verification_email(user.email, verification_link)

#             if email_response.status_code == 200:
#                 return Response({"message": "Verification email resent successfully"}, status=status.HTTP_200_OK)
#             else:
#                 return Response({"message": "Failed to resend verification email"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#         except User.DoesNotExist:
#             return Response({"error": "User with this email does not exist"}, status=status.HTTP_404_NOT_FOUND)


class LoginView(APIView):
    def post(self, request: Request) -> Response:
        email = request.data.get("email")
        password = request.data.get("password")

        if not email:
            return Response(
                {"errors": {"email": ["Email is required"]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not password:
            return Response(
                {"errors": {"password": ["Password is required"]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(email=email, password=password)

        if user is not None:
            if not user.email_verified:
                return Response(
                    {
                        "errors": {
                            "email": ["Please verify your email before logging in"]
                        }
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }
            )

        user_exists = User.objects.filter(email=email).exists()
        if user_exists:
            return Response(
                {"errors": {"password": ["Invalid password"]}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        else:
            return Response(
                {"errors": {"email": ["No account found with this email"]}},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            if not refresh_token:
                return Response(
                    {"error": "Refresh token is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except TokenError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print("This is the error", e)
            return Response(
                {"error": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed, edited and searched.
    """

    queryset = User.objects.exclude(is_superuser=True)
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPageNumberPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    lookup_field = "id"
    filterset_fields = ["id", "username", "email"]
    search_fields = ["id", "username", "email"]
    ordering_fields = ["id", "username", "email"]


class UserView(APIView):
    def get(self, request: Request) -> Response:
        token = request.COOKIES.get("jwt")

        if not token:
            raise AuthenticationFailed("Unauthenticated")

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Authentication Expired")

        user = User.objects.filter(id=payload["id"]).first()
        serializer = UserSerializer(user)
        return Response(serializer.data)


class CurrentUserDetailView(APIView):
    """
    An endpoint to get the current logged in users' details.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class ChangePasswordView(generics.UpdateAPIView):
    """
    An endpoint for changing password.
    """

    serializer_class = ChangePasswordSerializer
    model = User
    permission_classes = (IsAuthenticated,)

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Check old password
            if not self.object.check_password(serializer.data.get("old_password")):
                return Response(
                    {"old_password": ["Wrong password."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # set_password also hashes the password that the user will get
            self.object.set_password(serializer.data.get("new_password"))
            self.object.save()

            response = {
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Password updated successfully",
            }

            return Response(response)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
