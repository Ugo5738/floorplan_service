from django.urls import path

from floorplan import views

urlpatterns = [
    path(
        "analyze-floorplans/",
        views.FloorPlanAnalysisView.as_view(),
        name="analyze_floorplans",
    ),
]
