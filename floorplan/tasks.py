import csv
import io

import requests
from celery import shared_task
from django.conf import settings

from floorplan.models import (
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
from floorplan.utils.backup import backup_floorplan
from floorplan_service.config.logging_config import configure_logger

logger = configure_logger(__name__)


@shared_task(bind=True)
def process_floorplan_analysis(self, user_id, property_id, floorplans):
    """
    Task to initiate the analysis process via the analyzer API.
    In the new workflow, this only starts the process;
    the detailed results will be sent later via the webhook.
    """
    logger.info(
        "Starting floorplan analysis task for user_id=%s, property_id=%s",
        user_id,
        property_id,
    )
    payload = {
        "webhook_url": "https://floorplan.supersami.com/api/floorplan/webhook/",
        "user_id": user_id,
        "property_id": property_id,
        "floorplans": floorplans,
    }
    analyzer_url = "http://165.232.101.36/fpextractor"
    try:
        logger.info("Calling analyzer API at %s", analyzer_url)
        response = requests.post(analyzer_url, json=payload)
        response.raise_for_status()
        logger.info("Analyzer API initiated analysis successfully")
    except requests.RequestException as e:
        logger.error("Failed to call analyzer API: %s", str(e))
        return {"error": f"Failed to call analyzer API: {str(e)}"}

    logger.info(
        "Floorplan analysis initiation recorded for user_id=%s, property_id=%s",
        user_id,
        property_id,
    )
    return {"message": "Analysis initiated"}


@shared_task(bind=True)
def process_floorplan_webhook(self, analysis_data):
    """
    Processes the analysis payload sent to the webhook.

    For creation:
      - Expects: task="creation", message, user_id, property_id,
        and output_data as a list of new floorplans.

    For update:
      - Expects: task="update", user_id, property_id,
        and output_data as an object with the floorplan_id and floor update details.

    In the update case, the corresponding PlanFloor record (and its CSV data)
    is updated without deleting previous data.
    """
    task_type = analysis_data.get("task", "creation")
    user_id = analysis_data.get("user_id")
    property_id = analysis_data.get("property_id")

    if task_type == "creation":
        message = analysis_data.get("message", "No message provided")
        output_data = analysis_data.get("output_data", [])
        analysis_result = FloorPlanAnalysisResult.objects.create(
            message=message, user_id=user_id, property_id=property_id
        )
        logger.info(
            "Created FloorPlanAnalysisResult with id=%s via webhook (creation)",
            analysis_result.id,
        )

        for item in output_data:
            logger.info(
                "Processing floorplan (creation) with id=%s", item["floorplan_id"]
            )
            floorplan = FloorPlan.objects.create(
                analysis_result=analysis_result,
                floorplan_id=item["floorplan_id"],
                original_url=item["original_url"],
            )
            all_floors = item["all_floors"]
            all_floors_data = AllFloorsData.objects.create(
                floor_plan=floorplan,
                json_file_url=all_floors["json_file_url"],
                csv_url=all_floors["csv_url"],
                total_area_csv_url=all_floors["total_area_csv_url"],
                image_labelme_side_by_side_url=all_floors[
                    "image_labelme_side_by_side_url"
                ],
                notes=all_floors.get("notes", ""),
            )
            logger.info(
                "Created AllFloorsData for floorplan_id=%s", floorplan.floorplan_id
            )

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
                logger.info("Created PlanFloor for floor=%s", floor_data["floor"])

            csv_url = all_floors["csv_url"]
            try:
                logger.info("Downloading CSV data from %s", csv_url)
                csv_response = requests.get(csv_url)
                csv_response.raise_for_status()
                csv_content = csv_response.text
                csv_file = io.StringIO(csv_content)
                reader = csv.DictReader(csv_file)
                process_csv_data(reader, all_floors_data)
                logger.info(
                    "CSV data processed successfully for floorplan_id=%s",
                    floorplan.floorplan_id,
                )
            except requests.RequestException as e:
                logger.error("Failed to download CSV from %s: %s", csv_url, str(e))

            try:
                logger.info("Backing up floorplan with id=%s", floorplan.floorplan_id)
                backup_floorplan(floorplan)
                logger.info(
                    "Backup completed for floorplan_id=%s", floorplan.floorplan_id
                )
            except Exception as e:
                logger.error(
                    "Error backing up floorplan %s: %s", floorplan.floorplan_id, str(e)
                )

        logger.info(
            "Floorplan creation webhook processing completed for analysis_result id=%s",
            analysis_result.id,
        )
        return {
            "message": "Webhook creation processing completed",
            "analysis_id": analysis_result.id,
        }

    elif task_type == "update":
        output_data = analysis_data.get("output_data", {})
        floorplan_id = output_data.get("floorplan_id")
        floor_update_data = output_data.get("floors", {})
        if not floorplan_id or not floor_update_data:
            logger.error("Missing floorplan_id or floor update data in update payload")
            return {
                "error": "Missing floorplan_id or floor update data in update payload"
            }

        try:
            floorplan = FloorPlan.objects.get(floorplan_id=floorplan_id)
        except FloorPlan.DoesNotExist:
            logger.error("FloorPlan with id %s does not exist for update", floorplan_id)
            return {
                "error": f"FloorPlan with id {floorplan_id} does not exist for update"
            }

        floor_name = floor_update_data.get("floor")
        if not floor_name:
            logger.error("Floor name not provided in update payload")
            return {"error": "Floor name not provided in update payload"}

        try:
            plan_floor = floorplan.plan_floors.get(floor=floor_name)
            # Update existing PlanFloor fields
            plan_floor.label_me_url = floor_update_data.get(
                "label_me_url", plan_floor.label_me_url
            )
            plan_floor.json_file_url = floor_update_data.get(
                "json_file_url", plan_floor.json_file_url
            )
            plan_floor.image_url = floor_update_data.get(
                "image_url", plan_floor.image_url
            )
            plan_floor.labelme_image_url = floor_update_data.get(
                "labelme_image_url", plan_floor.labelme_image_url
            )
            plan_floor.csv_url = floor_update_data.get("csv_url", plan_floor.csv_url)
            plan_floor.image_side_by_side_url = floor_update_data.get(
                "image_side_by_side_url", plan_floor.image_side_by_side_url
            )
            plan_floor.save()
            logger.info(
                "Updated PlanFloor for floor %s in FloorPlan %s",
                floor_name,
                floorplan_id,
            )
        except PlanFloor.DoesNotExist:
            logger.info(
                "PlanFloor for floor %s does not exist in FloorPlan %s, creating new.",
                floor_name,
                floorplan_id,
            )
            plan_floor = PlanFloor.objects.create(
                floor_plan=floorplan,
                floor=floor_name,
                label_me_url=floor_update_data.get("label_me_url"),
                json_file_url=floor_update_data.get("json_file_url"),
                image_url=floor_update_data.get("image_url"),
                labelme_image_url=floor_update_data.get("labelme_image_url"),
                csv_url=floor_update_data.get("csv_url"),
                image_side_by_side_url=floor_update_data.get("image_side_by_side_url"),
            )

        # Update CSV data for this floor if AllFloorsData exists.
        all_floors_data = getattr(floorplan, "all_floors_data", None)
        if all_floors_data:
            csv_url = floor_update_data.get("csv_url")
            try:
                logger.info("Downloading updated CSV data from %s", csv_url)
                csv_response = requests.get(csv_url)
                csv_response.raise_for_status()
                csv_content = csv_response.text
                csv_file = io.StringIO(csv_content)
                reader = csv.DictReader(csv_file)
                update_csv_data(reader, all_floors_data, floor_name)
                logger.info(
                    "CSV data updated successfully for floor %s in FloorPlan %s",
                    floor_name,
                    floorplan_id,
                )
            except requests.RequestException as e:
                logger.error("Failed to download CSV from %s: %s", csv_url, str(e))
        else:
            logger.error("No AllFloorsData exists for FloorPlan %s", floorplan_id)

        try:
            logger.info(
                "Backing up updated FloorPlan with id=%s", floorplan.floorplan_id
            )
            backup_floorplan(floorplan)
            logger.info(
                "Backup completed for updated FloorPlan id=%s", floorplan.floorplan_id
            )
        except Exception as e:
            logger.error(
                "Error backing up updated FloorPlan %s: %s",
                floorplan.floorplan_id,
                str(e),
            )
        return {
            "message": "Floor update processing completed",
            "floorplan_id": floorplan_id,
        }

    else:
        logger.error("Unknown task type received in webhook: %s", task_type)
        return {"error": f"Unknown task type: {task_type}"}


def process_csv_data(reader, all_floors_data):
    """
    Process CSV rows for creation and store data in CSV-level models.
    """
    floor_cache = {}
    for row in reader:
        floor_name = row.get("Floor_Name")
        if not floor_name:
            continue
        if floor_name not in floor_cache:
            floor, _ = CsvFloor.objects.get_or_create(
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

        scaling_fields = ["Scale Metric", "Scale Imperial"]
        if any(row.get(field) for field in scaling_fields):
            CsvRoomScalingFactors.objects.create(
                room=room,
                scale_metric=(
                    float(row["Scale Metric"]) if row.get("Scale Metric") else None
                ),
                scale_imperial=(
                    float(row["Scale Imperial"]) if row.get("Scale Imperial") else None
                ),
            )


def update_csv_data(reader, all_floors_data, floor_name):
    """
    Update CSV data for a specific floor.
    This function updates the CsvFloor record (and associated CSV room data)
    for rows in the CSV matching the given floor name.
    """
    try:
        # Retrieve the most recent CsvFloor record for this floor.
        csv_floor = all_floors_data.csv_floors.filter(floor_name=floor_name).last()
        for row in reader:
            if row.get("Floor_Name") != floor_name:
                continue
            if csv_floor:
                csv_floor.calculated_total_area_metric = (
                    float(row["Calculated Floor Total Sq Area Metric"])
                    if row.get("Calculated Floor Total Sq Area Metric")
                    else None
                )
                csv_floor.calculated_total_area_imperial = (
                    float(row["Calculated Floor Total Sq Area Imperial"])
                    if row.get("Calculated Floor Total Sq Area Imperial")
                    else None
                )
                csv_floor.save()
            # Update or create each CsvRoom record based on a unique room identifier.
            room_id = float(row["Room_id"]) if row.get("Room_id") else None
            if room_id is not None:
                CsvRoom.objects.update_or_create(
                    floor=csv_floor,
                    room_id=room_id,
                    defaults={
                        "room_name": row.get("Room_Name"),
                        "is_segment": row.get("is_segment") or None,
                        "no_of_doors": (
                            float(row["No_of_door"]) if row.get("No_of_door") else None
                        ),
                        "no_of_windows": (
                            float(row["No_of_window"])
                            if row.get("No_of_window")
                            else None
                        ),
                        "no_of_room_points": (
                            float(row["No_of_room_points"])
                            if row.get("No_of_room_points")
                            else None
                        ),
                    },
                )
                # Similar update_or_create calls can be added for CsvRoomPixelData, CsvRoomDimensions, and CsvRoomScalingFactors.
        logger.info("CSV update completed for floor %s", floor_name)
    except Exception as e:
        logger.error("Error updating CSV data for floor %s: %s", floor_name, str(e))
