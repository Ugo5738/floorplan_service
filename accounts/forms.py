from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    UserCreationForm,
)
from django.utils.translation import gettext_lazy as _

from accounts.models import User


class UserLoginForm(AuthenticationForm):
    username = forms.EmailField(
        required=True,
        label=_("Email: "),
        widget=forms.TextInput(
            attrs={
                "type": "email",
                "class": "form-control form-control-user",
                "id": "exampleInputEmail",
                "aria-describedby": "emailHelp",
                "placeholder": "Enter Email Address...",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "type": "password",
                "class": "form-control form-control-user",
                "placeholder": "Password",
                "id": "exampleInputPassword",
            }
        )
    )

    # ADD REMEMBER ME
    class Meta:
        model = User
        fields = ("username", "password")


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        max_length=254,
        required=True,
        help_text=_("Required. Enter a valid email address."),
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-user",
                "id": "exampleInputEmail",
                "type": "email",
                "placeholder": "Email Address",
            }
        ),
    )
    first_name = forms.CharField(
        max_length=30,
        required=True,
        help_text=_("Enter First Name."),
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control form-control-user",
                "id": "exampleFirstName",
                "placeholder": "First Name",
            }
        ),
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        help_text=_("Enter Last Name."),
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "class": "form-control form-control-user",
                "id": "exampleLastName",
                "placeholder": "Last Name",
            }
        ),
    )
    password1 = forms.CharField(
        max_length=22,
        min_length=8,
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-user",
                "id": "exampleInputPassword",
                "type": "password",
                "placeholder": "Password",
                "maxlength": "22",
                "minlength": "8",
            }
        ),
    )
    password2 = forms.CharField(
        max_length=22,
        min_length=8,
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-user",
                "id": "exampleInputPassword",
                "type": "password",
                "placeholder": "Repeat Password",
                "maxlength": "22",
                "minlength": "8",
            }
        ),
    )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                f"This email address is already in use. Please use a different email."
            )
        return email

    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "password1",
            "password2",
            "phone",  # Not sure this is needed it is not in the front page
        )


class CustomPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {
                "class": "form-control form-control-user",
                "placeholder": "Enter Email Address...",
            }
        )


class ChangePasswordForm(PasswordChangeForm):
    old_password = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control mb-3", "placeholder": "Old Password"}
        ),
    )
    new_password1 = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control mb-3", "placeholder": "New Password"}
        ),
    )
    new_password2 = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control mb-3", "placeholder": "Confirm New Password"}
        ),
    )

    class Meta:
        model = User
        fields = (
            "old_password",
            "new_password1",
            "new_password2",
        )
