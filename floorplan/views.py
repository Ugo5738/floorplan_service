from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from floorplan.models import FloorPlanAnalysisResult, FloorPlan
from floorplan.serializers import (
    FloorPlanAnalysisResultSerializer,
    FloorPlanSerializer,
    PropertyOverviewSerializer
)
from floorplan.tasks import process_floorplan_analysis, process_floorplan_webhook


class FloorPlanAnalysisView(APIView):
    """
    Endpoint to initiate floorplan analysis.
    Expects a payload with "user_id", "property_id", and "floorplans".
    """

    def post(self, request):
        user_id = request.data.get("user_id")
        property_id = request.data.get("property_id")
        floorplans = request.data.get("floorplans")
        if not all([user_id, property_id, floorplans]):
            return Response(
                {"error": "Missing required fields: user_id, property_id, floorplans"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        process_floorplan_analysis.delay(user_id, property_id, floorplans)
        return Response(
            {"message": "Floorplan analysis initiated."},
            status=status.HTTP_202_ACCEPTED,
        )


class FloorPlanWebhookView(APIView):
    """
    Webhook endpoint to receive analysis results from the analyzer service.

    Supports two kinds of payloads:
      - Creation: expects "task": "creation", "message", "user_id", "property_id",
        and "output_data" (a list of new floorplans).
      - Update: expects "task": "update", "user_id", "property_id",
        and "output_data" as an object containing a "floorplan_id" and a "floors" update.
    """

    def post(self, request):
        data = request.data
        required_fields = ["task", "user_id", "property_id", "output_data"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return Response(
                {"error": f"Missing fields in payload: {missing_fields}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        process_floorplan_webhook.delay(data)
        return Response(
            {"message": "Webhook received. Processing initiated."},
            status=status.HTTP_202_ACCEPTED,
        )


class PropertyPagination(PageNumberPagination):
    """Custom pagination for property listings"""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


@api_view(['GET'])
def list_properties(request):
    """
    List all properties analyzed for the current user or filtered by user_id.
    
    Query parameters:
    - user_id: Filter properties by specific user ID
    - page: Page number for pagination
    - page_size: Number of items per page
    """
    # Extract query parameters
    user_id = request.query_params.get('user_id')
    
    # Build queryset with filters
    queryset = FloorPlanAnalysisResult.objects.all()
    if user_id:
        queryset = queryset.filter(user_id=user_id)
    
    # Annotate with floor plan count and order by creation date
    queryset = queryset.annotate(floor_plan_count=Count('floor_plans')).order_by('-created_at')
    
    # Apply pagination
    paginator = PropertyPagination()
    paginated_queryset = paginator.paginate_queryset(queryset, request)
    
    # Serialize data
    serializer = PropertyOverviewSerializer(paginated_queryset, many=True)
    
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
def get_property_detail(request, property_id):
    """
    Get detailed information for a specific property including all floor plans.
    
    Path parameters:
    - property_id: ID of the property to retrieve
    
    Query parameters:
    - user_id: Optional filter to ensure property belongs to specified user
    """
    # Extract query parameters
    user_id = request.query_params.get('user_id')
    
    # Build filter criteria
    filters = {'property_id': property_id}
    if user_id:
        filters['user_id'] = user_id
    
    # Get property or return 404
    try:
        property_analysis = FloorPlanAnalysisResult.objects.get(**filters)
    except FloorPlanAnalysisResult.DoesNotExist:
        return Response(
            {"error": f"Property with ID {property_id} not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Serialize and return data
    serializer = FloorPlanAnalysisResultSerializer(property_analysis)
    return Response(serializer.data)


@api_view(['GET'])
def get_floorplan_detail(request, floorplan_id):
    """
    Get detailed information for a specific floor plan.
    
    Path parameters:
    - floorplan_id: ID of the floor plan to retrieve
    
    Query parameters:
    - property_id: Optional filter to ensure floor plan belongs to specified property
    """
    # Extract query parameters
    property_id = request.query_params.get('property_id')
    
    # Build filter criteria
    filters = {'floorplan_id': floorplan_id}
    
    # Optional property filter using related fields
    if property_id:
        filters['analysis_result__property_id'] = property_id
    
    # Get floor plan or return 404
    try:
        floorplan = FloorPlan.objects.get(**filters)
    except FloorPlan.DoesNotExist:
        return Response(
            {"error": f"Floor plan with ID {floorplan_id} not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Serialize and return data
    serializer = FloorPlanSerializer(floorplan)
    return Response(serializer.data)
