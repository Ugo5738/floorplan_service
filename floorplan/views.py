# floorplan/views.py
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from floorplan.tasks import process_floorplan_analysis, process_floorplan_webhook


class FloorPlanAnalysisView(APIView):
    """
    Endpoint to initiate floorplan analysis.
    Expects payload with "user_id", "property_id", and "floorplans".
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

        # Enqueue the analysis task asynchronously.
        process_floorplan_analysis.delay(user_id, property_id, floorplans)
        return Response(
            {"message": "Floorplan analysis started."}, status=status.HTTP_202_ACCEPTED
        )


class FloorPlanWebhookView(APIView):
    """
    Webhook endpoint to receive analysis results from the analyzer service.
    Expects payload with "user_id", "property_id", "message", and "output_data".
    """

    def post(self, request):
        data = request.data
        required_fields = ["user_id", "property_id", "message", "output_data"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return Response(
                {"error": f"Missing fields in payload: {missing_fields}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Enqueue the webhook processing task.
        process_floorplan_webhook.delay(data)
        return Response(
            {"message": "Webhook received. Processing initiated."},
            status=status.HTTP_202_ACCEPTED,
        )
