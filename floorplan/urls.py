from django.urls import include, path
from rest_framework.routers import DefaultRouter

from floorplan import views

router = DefaultRouter()
# router.register(r"flooplans", views.FloorplanViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
