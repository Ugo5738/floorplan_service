from django.urls import path

from floorplan import views

urlpatterns = [
    # Existing endpoints
    path(
        "analyze-floorplans/",
        views.FloorPlanAnalysisView.as_view(),
        name="analyze_floorplans",
    ),
    path(
        "webhook/",
        views.FloorPlanWebhookView.as_view(),
        name="floorplan_webhook",
    ),
    
    # New property and floorplan query endpoints
    path(
        "properties/", 
        views.list_properties,
        name="property_list",
    ),
    path(
        "properties/<str:property_id>/", 
        views.get_property_detail,
        name="property_detail",
    ),
    path(
        "floorplans/<str:floorplan_id>/", 
        views.get_floorplan_detail,
        name="floorplan_detail",
    ),
]
