import csv
import io

import requests
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from floorplan.tasks import process_floorplan_analysis


class FloorPlanAnalysisView(APIView):
    def post(self, request):
        # Extract input data
        user_id = request.data.get("user_id")
        property_id = request.data.get("property_id")
        floorplans = request.data.get("floorplans")

        # Validate input
        if not all([user_id, property_id, floorplans]):
            return Response(
                {"error": "Missing required fields: user_id, property_id, floorplans"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Enqueue the background task
        process_floorplan_analysis.delay(user_id, property_id, floorplans)

        # Return immediately with an accepted status
        return Response(
            {"message": "Floorplan analysis started."},
            status=status.HTTP_202_ACCEPTED,
        )
