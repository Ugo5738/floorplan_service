from django.contrib import admin
from django.utils.html import format_html

from accounts.models import OrganizationProfile, User, UserToken


class UserAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "email",
        "username",
        "phone",
        "gender",
        "email_verified",
    ]
    list_filter = ["email_verified", "date_of_birth"]
    search_fields = ["email", "username", "phone"]


class OrganizationProfileAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "bio", "city", "address", "country", "zip_code"]
    list_filter = ["city", "country"]
    search_fields = ["name", "bio", "city", "address", "zip_code"]
    raw_id_fields = ["user"]


class UserTokenAdmin(admin.ModelAdmin):
    list_display = [
        "phone_number",
        "token",
        "created_at",
    ]
    list_filter = ["phone_number"]
    search_fields = ["phone_number"]


admin.site.register(User, UserAdmin)
admin.site.register(OrganizationProfile, OrganizationProfileAdmin)
admin.site.register(UserToken, UserTokenAdmin)
