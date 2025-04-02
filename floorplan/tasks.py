import csv
import io

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction

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
        "webhook_url": settings.FLOORPLAN_WEBHOOK_URL,
        "user_id": user_id,
        "property_id": property_id,
        "floorplans": floorplans,
    }
    analyzer_url = settings.FLOORPLAN_ANALYZER_URL
    try:
        logger.info("Analyzer payload being sent: %s", payload)
        logger.info("Calling analyzer API at %s", analyzer_url)
        response = requests.post(analyzer_url, json=payload)
        response.raise_for_status()
        logger.info("Analyzer API initiated analysis successfully")
    except requests.RequestException as e:
        logger.error("Failed to call analyzer API: %s", str(e))
        # Celery retry or marking failure
        raise self.retry(exc=e, countdown=60)
    except AttributeError:
        logger.error(
            "Missing FLOORPLAN_WEBHOOK_URL or FLOORPLAN_ANALYZER_URL in settings."
        )
        # Handle missing settings appropriately, maybe return error or raise specific exception
        return {"error": "Server configuration error: Missing required URLs."}

    logger.info(
        "Floorplan analysis initiation recorded for user_id=%s, property_id=%s",
        user_id,
        property_id,
    )
    return {"message": "Analysis initiated"}


@shared_task(bind=True)
@transaction.atomic
def process_floorplan_webhook(self, analysis_data):
    """
    Processes the analysis payload sent to the webhook.

    For creation:
      - Expects: task="creation", message, user_id, property_id,
        and output_data as a list of new floorplans.

    For update:
      - Expects: task="update", user_id, property_id,
        and output_data as an object containing the full data for the
        updated floorplan (similar structure to a single item in creation).

    Both tasks now use `update_or_create` where applicable to handle
    data consistently.
    """
    task_type = analysis_data.get("task", "creation")
    user_id = analysis_data.get("user_id")
    property_id = analysis_data.get("property_id")
    output_data = analysis_data.get("output_data")

    if not user_id or not property_id or not output_data:
        logger.error("Webhook received incomplete data: %s", analysis_data)
        return {
            "error": "Missing user_id, property_id, or output_data in webhook payload."
        }

    if task_type == "creation":
        message = analysis_data.get("message", "No message provided")
        # Ensure output_data is a list for creation
        if not isinstance(output_data, list):
            logger.error(
                "Webhook creation task expected list for output_data, got %s",
                type(output_data),
            )
            return {"error": "Invalid output_data format for creation task."}

        try:
            # Create a single AnalysisResult for this creation batch
            analysis_result, created = FloorPlanAnalysisResult.objects.get_or_create(
                user_id=user_id,
                property_id=property_id,
                # Use a unique identifier if possible, or rely on get_or_create with user/property
                defaults={"message": message},
            )
            action = "Created" if created else "Updated"
            logger.info(
                "%s FloorPlanAnalysisResult (ID: %s) for user %s, property %s.",
                action,
                analysis_result.id,
                user_id,
                property_id,
            )
        except Exception as e:
            # Catch potential errors during the update_or_create itself
            logger.error(
                "Error during update_or_create for FloorPlanAnalysisResult (user: %s, property: %s): %s",
                user_id,
                property_id,
                str(e),
                exc_info=True,
            )
            return {"error": "Failed to process analysis result header."}
        # --- End update_or_create block ---

        logger.info("Processing output data: %s", output_data)

        for item in output_data:
            floorplan_id = item.get("floorplan_id")
            original_url = item.get("original_url")
            all_floors_item = item.get("all_floors")
            floors_list = item.get("floors", [])

            if not floorplan_id or not original_url or not all_floors_item:
                logger.warning(
                    "Skipping item in creation due to missing data: %s", item
                )
                continue

            logger.info("Processing floorplan (creation) with id=%s", floorplan_id)

            # Create or update FloorPlan (useful if somehow retried)
            floorplan, fp_created = FloorPlan.objects.update_or_create(
                floorplan_id=floorplan_id,
                defaults={
                    "analysis_result": analysis_result,
                    "original_url": original_url,
                },
            )
            action_fp = "Created" if fp_created else "Updated"
            logger.info("%s FloorPlan with id=%s", action_fp, floorplan_id)

            # Create or update AllFloorsData
            all_floors_data, afd_created = AllFloorsData.objects.update_or_create(
                floor_plan=floorplan,
                defaults={
                    "json_file_url": all_floors_item.get("json_file_url"),
                    "csv_url": all_floors_item.get("csv_url"),
                    "total_area_csv_url": all_floors_item.get("total_area_csv_url"),
                    "image_labelme_side_by_side_url": all_floors_item.get(
                        "image_labelme_side_by_side_url"
                    ),
                    "notes": all_floors_item.get("notes", ""),
                },
            )
            action_afd = "Created" if afd_created else "Updated"
            logger.info(
                "%s AllFloorsData for floorplan_id=%s",
                action_afd,
                floorplan.floorplan_id,
            )

            # Process PlanFloors
            existing_plan_floor_names = set(
                floorplan.plan_floors.values_list("floor", flat=True)
            )
            current_plan_floor_names = set()
            for floor_data in floors_list:
                floor_name = floor_data.get("floor")
                if not floor_name:
                    logger.warning(
                        "Skipping plan floor item due to missing floor name: %s",
                        floor_data,
                    )
                    continue
                current_plan_floor_names.add(floor_name)
                pf, pf_created = PlanFloor.objects.update_or_create(
                    floor_plan=floorplan,
                    floor=floor_name,  # Assumes (floor_plan, floor) is unique
                    defaults={
                        "label_me_url": floor_data.get("label_me_url"),
                        "json_file_url": floor_data.get("json_file_url"),
                        "image_url": floor_data.get("image_url"),
                        "labelme_image_url": floor_data.get("labelme_image_url"),
                        "csv_url": floor_data.get(
                            "csv_url"
                        ),  # Might be floor-specific CSV
                        "image_side_by_side_url": floor_data.get(
                            "image_side_by_side_url"
                        ),
                    },
                )
                action_pf = "Created" if pf_created else "Updated"
                logger.info("%s PlanFloor for floor=%s", action_pf, floor_name)

            # Optional: Remove PlanFloors that are no longer present in the data
            floors_to_remove = existing_plan_floor_names - current_plan_floor_names
            if floors_to_remove:
                logger.info(
                    "Removing old PlanFloors not in new data: %s", floors_to_remove
                )
                floorplan.plan_floors.filter(floor__in=floors_to_remove).delete()

            # Process the main CSV data
            csv_url = all_floors_item.get("csv_url")
            if csv_url:
                try:
                    logger.info("Downloading CSV data from %s", csv_url)
                    csv_response = requests.get(csv_url)
                    csv_response.raise_for_status()
                    csv_content = csv_response.text
                    csv_file = io.StringIO(csv_content)
                    reader = csv.DictReader(csv_file)
                    # Use the consolidated processing function
                    process_csv_data(reader, all_floors_data)
                    logger.info(
                        "CSV data processed successfully for floorplan_id=%s",
                        floorplan.floorplan_id,
                    )
                except requests.RequestException as e:
                    logger.error(
                        "Failed to download or process CSV from %s: %s", csv_url, str(e)
                    )
                except Exception as e:
                    logger.error(
                        "Error processing CSV data for floorplan %s: %s",
                        floorplan_id,
                        str(e),
                        exc_info=True,
                    )
            else:
                logger.warning(
                    "No main CSV URL provided for floorplan_id=%s", floorplan_id
                )

            # Backup the processed floorplan state
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
        # Assume output_data is a dictionary representing the full updated floorplan
        if not isinstance(output_data, dict):
            logger.error(
                "Webhook update task expected dict for output_data, got %s",
                type(output_data),
            )
            return {"error": "Invalid output_data format for update task."}

        floorplan_id = output_data.get("floorplan_id")
        original_url = output_data.get("original_url")  # Get original URL if provided
        all_floors_item = output_data.get("all_floors")
        floors_list = output_data.get("floors", [])

        if not floorplan_id or not all_floors_item:
            logger.error(
                "Missing floorplan_id or all_floors data in update payload: %s",
                output_data,
            )
            return {
                "error": "Missing floorplan_id or all_floors data in update payload"
            }

        try:
            # Find the existing FloorPlan
            floorplan = FloorPlan.objects.select_related("analysis_result").get(
                floorplan_id=floorplan_id
            )
            # Optionally update original_url if provided in the update
            if original_url and floorplan.original_url != original_url:
                floorplan.original_url = original_url
                floorplan.save(update_fields=["original_url"])
                logger.info("Updated original_url for FloorPlan %s", floorplan_id)

        except FloorPlan.DoesNotExist:
            logger.error("FloorPlan with id %s does not exist for update", floorplan_id)
            return {
                "error": f"FloorPlan with id {floorplan_id} does not exist for update"
            }

        logger.info("Processing update for FloorPlan id=%s", floorplan_id)

        # Update or Create AllFloorsData
        all_floors_data, afd_created = AllFloorsData.objects.update_or_create(
            floor_plan=floorplan,
            defaults={
                "json_file_url": all_floors_item.get("json_file_url"),
                "csv_url": all_floors_item.get("csv_url"),
                "total_area_csv_url": all_floors_item.get("total_area_csv_url"),
                "image_labelme_side_by_side_url": all_floors_item.get(
                    "image_labelme_side_by_side_url"
                ),
                "notes": all_floors_item.get("notes", ""),
            },
        )
        if afd_created:
            logger.info(
                "Created AllFloorsData during update for floorplan_id=%s", floorplan_id
            )
        else:
            logger.info("Updated AllFloorsData for floorplan_id=%s", floorplan_id)

        # Update or Create PlanFloors, remove old ones
        existing_plan_floor_names = set(
            floorplan.plan_floors.values_list("floor", flat=True)
        )
        current_plan_floor_names = set()
        for floor_data in floors_list:
            floor_name = floor_data.get("floor")
            if not floor_name:
                logger.warning(
                    "Skipping plan floor item due to missing floor name: %s", floor_data
                )
                continue
            current_plan_floor_names.add(floor_name)

            pf, pf_created = PlanFloor.objects.update_or_create(
                floor_plan=floorplan,
                floor=floor_name,
                defaults={
                    "label_me_url": floor_data.get("label_me_url"),
                    "json_file_url": floor_data.get("json_file_url"),
                    "image_url": floor_data.get("image_url"),
                    "labelme_image_url": floor_data.get("labelme_image_url"),
                    "csv_url": floor_data.get(
                        "csv_url"
                    ),  # Use floor-specific if needed, else null?
                    "image_side_by_side_url": floor_data.get("image_side_by_side_url"),
                },
            )
            if pf_created:
                logger.info("Created PlanFloor for floor=%s during update", floor_name)
            else:
                logger.info("Updated PlanFloor for floor=%s", floor_name)

        # Optional: Remove PlanFloors that are no longer present in the update data
        floors_to_remove = existing_plan_floor_names - current_plan_floor_names
        if floors_to_remove:
            logger.info(
                "Removing old PlanFloors not in update data: %s", floors_to_remove
            )
            floorplan.plan_floors.filter(floor__in=floors_to_remove).delete()

        # Process the main CSV data using the consolidated function
        csv_url = all_floors_item.get("csv_url")
        if csv_url:
            try:
                logger.info("Downloading updated CSV data from %s", csv_url)
                csv_response = requests.get(csv_url)
                csv_response.raise_for_status()
                csv_content = csv_response.text
                csv_file = io.StringIO(csv_content)
                reader = csv.DictReader(csv_file)
                # Use the consolidated processing function
                process_csv_data(reader, all_floors_data)
                logger.info(
                    "CSV data updated successfully via main CSV for FloorPlan %s",
                    floorplan_id,
                )
            except requests.RequestException as e:
                logger.error(
                    "Failed to download or process CSV from %s: %s", csv_url, str(e)
                )
            except Exception as e:  # Catch broader errors during CSV processing
                logger.error(
                    "Error processing CSV data for floorplan %s during update: %s",
                    floorplan_id,
                    str(e),
                )

        else:
            logger.warning(
                "No main CSV URL provided in update for floorplan_id=%s", floorplan_id
            )
            # Consider if you need to clear old CSV data if no CSV URL is provided in update
            # all_floors_data.csv_floors.all().delete() # Example: Uncomment to clear if needed

        # Backup the updated floorplan state
        try:
            logger.info(
                "Backing up updated FloorPlan with id=%s", floorplan.floorplan_id
            )
            backup_floorplan(floorplan)  # Backup contains the latest state
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
    Process CSV rows using update_or_create for all CSV-level models.
    This function handles both initial creation and full updates based on
    the provided all_floors_data instance. It also removes rooms for a floor
    that are no longer present in the current CSV data for that floor.
    """
    # Keep track of floors and rooms processed in this CSV run
    processed_floor_names = set()
    processed_room_ids_by_floor = {}  # {floor_name: {room_id1, room_id2, ...}}

    floor_cache = {}  # Cache CsvFloor instances for efficiency within this run

    for row in reader:
        floor_name = row.get("Floor_Name")
        room_id_str = row.get("Room_id")

        if not floor_name:
            logger.warning("Skipping CSV row due to missing Floor_Name: %s", row)
            continue
        if not room_id_str:
            logger.warning("Skipping CSV row due to missing Room_id: %s", row)
            continue

        try:
            # Use float for Room_id as in the model, handle potential ValueError
            room_id = float(room_id_str)
        except ValueError:
            logger.warning(
                "Skipping CSV row due to invalid Room_id format '%s': %s",
                room_id_str,
                row,
            )
            continue

        processed_floor_names.add(floor_name)
        if floor_name not in processed_room_ids_by_floor:
            processed_room_ids_by_floor[floor_name] = set()
        processed_room_ids_by_floor[floor_name].add(room_id)

        # --- Process CsvFloor ---
        if floor_name not in floor_cache:
            floor, f_created = CsvFloor.objects.update_or_create(
                all_floors_data=all_floors_data,
                floor_name=floor_name,
                defaults={
                    "calculated_total_area_metric": (
                        float(row["Calculated Floor Total Sq Area Metric"])
                        if row.get("Calculated Floor Total Sq Area Metric")
                        not in [None, "", "nan", "unknown"]  # Check for invalid values
                        else None
                    ),
                    "calculated_total_area_imperial": (
                        float(row["Calculated Floor Total Sq Area Imperial"])
                        if row.get("Calculated Floor Total Sq Area Imperial")
                        not in [None, "", "nan", "unknown"]
                        else None
                    ),
                },
            )
            floor_cache[floor_name] = floor
            action = "Created" if f_created else "Updated"
            # logger.debug("%s CsvFloor: %s", action, floor_name) # Optional detailed logging
        else:
            floor = floor_cache[floor_name]  # Use cached instance

        # --- Process CsvRoom ---
        room, r_created = CsvRoom.objects.update_or_create(
            floor=floor,
            room_id=room_id,  # Use room_id as the unique key within a floor
            defaults={
                "room_name": row.get("Room_Name"),
                "is_segment": row.get("is_segment") or None,
                "no_of_doors": (
                    float(row["No_of_door"])
                    if row.get("No_of_door") not in [None, "", "nan"]
                    else None
                ),
                "no_of_windows": (
                    float(row["No_of_window"])
                    if row.get("No_of_window") not in [None, "", "nan"]
                    else None
                ),
                "no_of_room_points": (
                    float(row["No_of_room_points"])
                    if row.get("No_of_room_points") not in [None, "", "nan"]
                    else None
                ),
            },
        )
        action = "Created" if r_created else "Updated"
        # logger.debug("%s CsvRoom: %s (ID: %s)", action, row.get("Room_Name"), room_id)

        # --- Process CsvRoomPixelData ---
        pixel_defaults = {
            "min_x_pixels": (
                float(row["Min X Pixels"])
                if row.get("Min X Pixels") not in [None, "", "nan"]
                else None
            ),
            "min_y_pixels": (
                float(row["Min Y Pixels"])
                if row.get("Min Y Pixels") not in [None, "", "nan"]
                else None
            ),
            "max_x_pixels": (
                float(row["Max X Pixels"])
                if row.get("Max X Pixels") not in [None, "", "nan"]
                else None
            ),
            "max_y_pixels": (
                float(row["Max Y Pixels"])
                if row.get("Max Y Pixels") not in [None, "", "nan"]
                else None
            ),
            "max_area_pixels": (
                float(row["Max Area Pixels"])
                if row.get("Max Area Pixels") not in [None, "", "nan"]
                else None
            ),
            "actual_area_pixels": (
                float(row["Actual Area Pixels"])
                if row.get("Actual Area Pixels") not in [None, "", "nan"]
                else None
            ),
            "pixel_ratio": (
                float(row["Pixel ratio"])
                if row.get("Pixel ratio") not in [None, "", "nan"]
                else None
            ),
        }
        # Only update/create if there's any non-null pixel data in the row
        if any(v is not None for v in pixel_defaults.values()):
            CsvRoomPixelData.objects.update_or_create(
                room=room, defaults=pixel_defaults
            )
        else:
            # Optional: Delete pixel data if it exists but the row has no values now
            CsvRoomPixelData.objects.filter(room=room).delete()

        # --- Process CsvRoomDimensions ---
        dimension_defaults = {
            "dimensions_imperial": (
                row["dimensions_imperial"]
                if row.get("dimensions_imperial")
                and row["dimensions_imperial"].lower() != "unknown"
                else None
            ),
            "dimensions_metric": (
                row["dimensions_metric"]
                if row.get("dimensions_metric")
                and row["dimensions_metric"].lower() != "unknown"
                else None
            ),
            "max_area_metric": (
                float(row["Max Area Metric"])
                if row.get("Max Area Metric") not in [None, "", "nan"]
                else None
            ),
            "max_area_imperial": (
                float(row["Max Area Imperial"])
                if row.get("Max Area Imperial") not in [None, "", "nan"]
                else None
            ),
            "calculated_sq_area_metric": (
                float(row["Calculated Sq Area Metric"])
                if row.get("Calculated Sq Area Metric") not in [None, "", "nan"]
                else None
            ),
            "calculated_area_imperial": (
                float(row["calculated_area_imperial"])
                if row.get("calculated_area_imperial") not in [None, "", "nan"]
                else None
            ),
            # Note: Floor Total Area fields are in CsvFloor model now, not here.
            # Remove them if they were previously in CsvRoomDimensions defaults.
        }
        # Only update/create if there's any non-null dimension data in the row
        if any(v is not None for v in dimension_defaults.values()):
            CsvRoomDimensions.objects.update_or_create(
                room=room, defaults=dimension_defaults
            )
        else:
            # Optional: Delete dimension data if it exists but the row has no values now
            CsvRoomDimensions.objects.filter(room=room).delete()

        # --- Process CsvRoomScalingFactors ---
        scaling_defaults = {
            "scale_metric": (
                float(row["Scale Metric"])
                if row.get("Scale Metric") not in [None, "", "nan"]
                else None
            ),
            "scale_imperial": (
                float(row["Scale Imperial"])
                if row.get("Scale Imperial") not in [None, "", "nan"]
                else None
            ),
        }
        # Only update/create if there's any non-null scaling data in the row
        if any(v is not None for v in scaling_defaults.values()):
            CsvRoomScalingFactors.objects.update_or_create(
                room=room, defaults=scaling_defaults
            )
        else:
            # Optional: Delete scaling data if it exists but the row has no values now
            CsvRoomScalingFactors.objects.filter(room=room).delete()

    # --- Clean up old data ---
    # Get all CsvFloors associated with this AllFloorsData
    existing_floors = all_floors_data.csv_floors.all()

    # Delete CsvFloors (and their cascade-deleted rooms) that were NOT in this CSV run
    floors_to_delete = existing_floors.exclude(floor_name__in=processed_floor_names)
    if floors_to_delete.exists():
        logger.info(
            "Deleting CsvFloors (and related rooms) no longer present in CSV: %s",
            list(floors_to_delete.values_list("floor_name", flat=True)),
        )
        floors_to_delete.delete()

    # For floors that WERE processed, delete rooms that were NOT in this CSV run
    for floor_name, processed_room_ids in processed_room_ids_by_floor.items():
        if floor_name in floor_cache:  # Ensure the floor object is available
            csv_floor = floor_cache[floor_name]
            rooms_to_delete = csv_floor.rooms.exclude(room_id__in=processed_room_ids)
            if rooms_to_delete.exists():
                logger.info(
                    "Deleting CsvRooms for floor '%s' no longer present in CSV: %s",
                    floor_name,
                    list(rooms_to_delete.values_list("room_id", flat=True)),
                )
                rooms_to_delete.delete()

    logger.info(
        "CSV data processing finished for AllFloorsData id=%s", all_floors_data.id
    )
