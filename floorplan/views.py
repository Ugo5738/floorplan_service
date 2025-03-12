import csv
import io

import requests
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AllFloorsData,
    CsvFloor,
    CsvRoom,
    CsvRoomDimensions,
    CsvRoomPixelData,
    CsvRoomScalingFactors,
    FloorPlan,
    FloorPlanAnalysisResult,
    PlanFloor,
)


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

        payload = {
            "user_id": user_id,
            "property_id": property_id,
            "floorplans": floorplans,
        }

        # Call the floorplan analyzer API (replace with actual URL)
        analyzer_url = "http://165.232.101.36/fpextractor"  # Update with real endpoint
        try:
            response = requests.post(analyzer_url, json=payload)
            response.raise_for_status()
            analysis_data = response.json()
            print("this is the analysis_data: ", analysis_data)
        except requests.RequestException as e:
            return Response(
                {"error": f"Failed to call floorplan analyzer API: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Process the analysis output
        message = analysis_data.get("message", "No message provided")
        analysis_result = FloorPlanAnalysisResult.objects.create(
            message=message, user_id=user_id, property_id=property_id
        )

        output_data = analysis_data.get("output_data", [])
        for item in output_data:
            # Create FloorPlan instance
            floorplan = FloorPlan.objects.create(
                analysis_result=analysis_result,
                floorplan_id=item["floorplan_id"],
                original_url=item["original_url"],
            )

            # Create AllFloorsData instance
            all_floors = item["all_floors"]
            all_floors_data = AllFloorsData.objects.create(
                floor_plan=floorplan,
                json_file_url=all_floors["json_file_url"],
                csv_url=all_floors["csv_url"],
                total_area_csv_url=all_floors["total_area_csv_url"],
                image_labelme_side_by_side_url=all_floors[
                    "image_labelme_side_by_side_url"
                ],
                notes=all_floors["notes"],
            )

            # Create PlanFloor instances for each floor
            for floor_data in item["floors"]:
                PlanFloor.objects.create(
                    floor_plan=floorplan,
                    floor=floor_data["floor"],
                    label_me_url=floor_data["label_me_url"],
                    json_file_url=floor_data["json_file_url"],
                    image_url=floor_data["image_url"],
                    labelme_image_url=floor_data["labelme_image_url"],
                    csv_url=floor_data["csv_url"],
                    image_side_by_side_url=floor_data["image_side_by_side_url"],
                )

            # Download and process the all_floors.csv
            csv_url = all_floors["csv_url"]
            try:
                csv_response = requests.get(csv_url)
                csv_response.raise_for_status()
                csv_content = csv_response.text
                csv_file = io.StringIO(csv_content)
                reader = csv.DictReader(csv_file)
                self.process_csv_data(reader, all_floors_data)
            except requests.RequestException as e:
                # Log the error and continue (or adjust based on requirements)
                return Response(
                    {"warning": f"Failed to download CSV from {csv_url}: {str(e)}"},
                    status=status.HTTP_206_PARTIAL_CONTENT,
                )

        return Response(
            {"message": "Analysis completed", "analysis_id": analysis_result.id},
            status=status.HTTP_201_CREATED,
        )

    def process_csv_data(self, reader, all_floors_data):
        """Process CSV rows and store data in CSV-level models."""
        floor_cache = {}
        for row in reader:
            floor_name = row.get("Floor_Name")
            if not floor_name:  # Skip empty rows
                continue

            # Get or create CsvFloor
            if floor_name not in floor_cache:
                floor, created = CsvFloor.objects.get_or_create(
                    all_floors_data=all_floors_data,
                    floor_name=floor_name,
                    defaults={
                        "calculated_total_area_metric": (
                            float(row["Calculated Floor Total Sq Area Metric"])
                            if row.get("Calculated Floor Total Sq Area Metric")
                            else None
                        ),
                        "calculated_total_area_imperial": (
                            float(row["Calculated Floor Total Sq Area Imperial"])
                            if row.get("Calculated Floor Total Sq Area Imperial")
                            else None
                        ),
                    },
                )
                floor_cache[floor_name] = floor
            else:
                floor = floor_cache[floor_name]

            # Create CsvRoom
            room = CsvRoom(
                floor=floor,
                room_name=row.get("Room_Name"),
                is_segment=row.get("is_segment") or None,
                room_id=float(row["Room_id"]) if row.get("Room_id") else None,
                no_of_doors=float(row["No_of_door"]) if row.get("No_of_door") else None,
                no_of_windows=(
                    float(row["No_of_window"]) if row.get("No_of_window") else None
                ),
                no_of_room_points=(
                    float(row["No_of_room_points"])
                    if row.get("No_of_room_points")
                    else None
                ),
            )
            room.save()

            # Create CsvRoomPixelData if data exists
            pixel_fields = [
                "Min X Pixels",
                "Min Y Pixels",
                "Max X Pixels",
                "Max Y Pixels",
                "Max Area Pixels",
                "Actual Area Pixels",
                "Pixel ratio",
            ]
            if any(row.get(field) for field in pixel_fields):
                CsvRoomPixelData.objects.create(
                    room=room,
                    min_x_pixels=(
                        float(row["Min X Pixels"]) if row.get("Min X Pixels") else None
                    ),
                    min_y_pixels=(
                        float(row["Min Y Pixels"]) if row.get("Min Y Pixels") else None
                    ),
                    max_x_pixels=(
                        float(row["Max X Pixels"]) if row.get("Max X Pixels") else None
                    ),
                    max_y_pixels=(
                        float(row["Max Y Pixels"]) if row.get("Max Y Pixels") else None
                    ),
                    max_area_pixels=(
                        float(row["Max Area Pixels"])
                        if row.get("Max Area Pixels")
                        else None
                    ),
                    actual_area_pixels=(
                        float(row["Actual Area Pixels"])
                        if row.get("Actual Area Pixels")
                        else None
                    ),
                    pixel_ratio=(
                        float(row["Pixel ratio"]) if row.get("Pixel ratio") else None
                    ),
                )

            # Create CsvRoomDimensions if data exists
            dimension_fields = [
                "dimensions_imperial",
                "dimensions_metric",
                "Max Area Metric",
                "Max Area Imperial",
                "Calculated Sq Area Metric",
                "calculated_area_imperial",
            ]
            if any(row.get(field) for field in dimension_fields):
                CsvRoomDimensions.objects.create(
                    room=room,
                    dimensions_imperial=(
                        row["dimensions_imperial"]
                        if row.get("dimensions_imperial")
                        and row["dimensions_imperial"] != "unknown"
                        else None
                    ),
                    dimensions_metric=(
                        row["dimensions_metric"]
                        if row.get("dimensions_metric")
                        and row["dimensions_metric"] != "unknown"
                        else None
                    ),
                    max_area_metric=(
                        float(row["Max Area Metric"])
                        if row.get("Max Area Metric")
                        else None
                    ),
                    max_area_imperial=(
                        float(row["Max Area Imperial"])
                        if row.get("Max Area Imperial")
                        else None
                    ),
                    calculated_sq_area_metric=(
                        float(row["Calculated Sq Area Metric"])
                        if row.get("Calculated Sq Area Metric")
                        else None
                    ),
                    calculated_area_imperial=(
                        float(row["calculated_area_imperial"])
                        if row.get("calculated_area_imperial")
                        else None
                    ),
                )

            # Create CsvRoomScalingFactors if data exists
            scaling_fields = ["Scale Metric", "Scale Imperial"]
            if any(row.get(field) for field in scaling_fields):
                CsvRoomScalingFactors.objects.create(
                    room=room,
                    scale_metric=(
                        float(row["Scale Metric"]) if row.get("Scale Metric") else None
                    ),
                    scale_imperial=(
                        float(row["Scale Imperial"])
                        if row.get("Scale Imperial")
                        else None
                    ),
                )
