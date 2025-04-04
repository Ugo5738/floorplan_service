import csv
import io

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from floorplan.models import (
    AllFloorsCsvRawRow,
    AllFloorsData,
    CsvFloor,
    CsvRoom,
    CsvRoomDimensions,
    CsvRoomPixelData,
    CsvRoomScalingFactors,
    FloorPlan,
    FloorPlanAnalysisResult,
    PlanFloor,
    TotalAreaData,
)
from floorplan.utils.backup import backup_floorplan
from floorplan_service.config.logging_config import configure_logger

logger = configure_logger(__name__)


# === Helper Constants ===
INVALID_FLOAT_VALUES = frozenset([None, "", "nan", "unknown", "Unknown"])
INVALID_DIMENSION_VALUES = frozenset([None, "", "unknown", "Unknown"])
INVALID_INT_VALUES = frozenset([None, "", "nan", "unknown", "Unknown"])
INVALID_STRING_VALUES = frozenset([None])  # Only None is truly invalid for strings

# === Helper Functions ===


def safe_float(value):
    """Safely converts a value to float, returning None for invalid inputs."""
    if isinstance(value, str):
        value = value.strip()
    if value in INVALID_FLOAT_VALUES:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_int(value):
    """
    Safely attempts to convert a value to an integer.
    Handles None, empty strings, 'nan', 'unknown', and float strings like '5.0'.
    Returns None if conversion is not possible or value is invalid.
    """
    if isinstance(value, str):
        value = value.strip()
    if value in INVALID_INT_VALUES:
        return None
    try:
        # Convert to float first to handle strings like '5.0', then to int
        return int(float(value))
    except (ValueError, TypeError):
        return None


def safe_dimension(value):
    """Returns the value if it's a valid dimension string, else None."""
    if isinstance(value, str):
        value = value.strip()
        if (
            value.lower() in INVALID_DIMENSION_VALUES
        ):  # Case-insensitive check for 'unknown'
            return None
    elif value in INVALID_DIMENSION_VALUES:  # Handles None, '' directly
        return None
    return value  # Return the original (stripped) string if valid


def safe_string(value):
    """Returns the string value, or None if the input is None."""
    if isinstance(value, str):
        return (
            value.strip() if value.strip() else None
        )  # Treat empty string as None? Decide policy. Or just return strip()
    return value if value not in INVALID_STRING_VALUES else None


# === Celery Tasks ===


@shared_task(bind=True)
def process_floorplan_analysis(self, user_id, property_id, floorplans):
    """
    Task to initiate the analysis process via the analyzer API.
    """
    logger.info(
        "Starting floorplan analysis task for user_id=%s, property_id=%s",
        user_id,
        property_id,
    )
    webhook_url = settings.FLOORPLAN_WEBHOOK_URL
    analyzer_url = settings.FLOORPLAN_ANALYZER_URL

    if not webhook_url or not analyzer_url:
        logger.error(
            "Missing FLOORPLAN_WEBHOOK_URL or FLOORPLAN_ANALYZER_URL in settings."
        )
        # Consider raising an exception or returning an error state if critical
        return {"error": "Server configuration error: Missing required URLs."}

    payload = {
        "webhook_url": webhook_url,
        "user_id": user_id,
        "property_id": property_id,
        "floorplans": floorplans,
    }

    try:
        logger.info(
            "Calling analyzer API at %s with payload: %s", analyzer_url, payload
        )
        response = requests.post(analyzer_url, json=payload, timeout=60)  # Add timeout
        response.raise_for_status()
        logger.info("Analyzer API call successful, analysis initiated.")
    except requests.Timeout:
        logger.error("Timeout calling analyzer API at %s", analyzer_url)
        raise self.retry(countdown=60, max_retries=5)
    except requests.RequestException as e:
        logger.error(
            "Failed to call analyzer API: %s (Status: %s)",
            str(e),
            getattr(e.response, "status_code", "N/A"),
        )
        # Optionally log response body if available and useful: logger.error("Response: %s", e.response.text)
        raise self.retry(exc=e, countdown=60, max_retries=5)  # Retry on failures

    logger.info(
        "Floorplan analysis initiation task completed for user_id=%s, property_id=%s",
        user_id,
        property_id,
    )
    return {"message": "Analysis initiated successfully"}


@shared_task(bind=True)
@transaction.atomic  # Ensure all DB operations within this task are atomic
def process_floorplan_webhook(self, analysis_data):
    """
    Processes the analysis payload sent to the webhook (entry point).
    Delegates processing based on the task type ('creation' or 'update').
    """
    task_type = analysis_data.get("task")
    user_id = analysis_data.get("user_id")
    property_id = analysis_data.get("property_id")
    output_data = analysis_data.get("output_data")

    # --- Basic Validation ---
    if not all([task_type, user_id, property_id, output_data]):
        missing = [
            k
            for k, v in {
                "task": task_type,
                "user_id": user_id,
                "property_id": property_id,
                "output_data": output_data,
            }.items()
            if not v
        ]
        logger.error(
            "Webhook received incomplete data. Missing: %s. Payload: %s",
            missing,
            analysis_data,
        )
        return {"error": f"Missing required fields in webhook payload: {missing}"}

    logger.info(
        "Processing webhook task '%s' for user '%s', property '%s'",
        task_type,
        user_id,
        property_id,
    )

    # --- Task Delegation ---
    try:
        if task_type == "creation":
            result = _handle_creation_task(analysis_data)
        elif task_type == "update":
            result = _handle_update_task(analysis_data)
        else:
            logger.error("Unknown task type received in webhook: %s", task_type)
            result = {"error": f"Unknown task type: {task_type}"}

        logger.info(
            "Webhook processing completed for task '%s', user '%s', property '%s'. Result: %s",
            task_type,
            user_id,
            property_id,
            result,
        )
        return result

    except Exception as e:
        # Catch unexpected errors during processing
        logger.exception(  # Use exception to include traceback
            "Unhandled error during webhook processing for task '%s', user '%s', property '%s': %s",
            task_type,
            user_id,
            property_id,
            str(e),
        )
        # Decide if retry is appropriate or return error
        # For now, return error to avoid potential infinite loops on bad data
        return {"error": f"Internal server error during webhook processing: {str(e)}"}


# --- Private Helper Functions for Webhook Processing ---


def _handle_creation_task(analysis_data):
    """Handles the 'creation' task logic."""
    user_id = analysis_data["user_id"]
    property_id = analysis_data["property_id"]
    output_data = analysis_data["output_data"]
    message = analysis_data.get("message", "Floorplan batch created")  # Default message

    if not isinstance(output_data, list):
        logger.error(
            "Webhook 'creation' task expected list for output_data, got %s",
            type(output_data),
        )
        return {"error": "Invalid output_data format for creation task."}

    # 1. Get or Create the main Analysis Result
    analysis_result, created = FloorPlanAnalysisResult.objects.update_or_create(
        user_id=user_id,
        property_id=property_id,
        defaults={
            "message": message,
            "created_at": timezone.now(),
        },  # Update timestamp on update too?
    )
    action = "Created" if created else "Updated"
    logger.info(
        "%s FloorPlanAnalysisResult (ID: %s) for user %s, property %s.",
        action,
        analysis_result.id,
        user_id,
        property_id,
    )

    processed_floorplan_ids = set()
    # 2. Process each floorplan item in the list
    for item_data in output_data:
        floorplan_id = item_data.get("floorplan_id")
        if not floorplan_id:
            logger.warning(
                "Skipping item in creation due to missing floorplan_id: %s", item_data
            )
            continue

        try:
            _process_single_floorplan_data(item_data, analysis_result)
            processed_floorplan_ids.add(floorplan_id)
        except Exception as e:
            logger.exception(
                "Error processing floorplan item (ID: %s) during creation for AnalysisResult %s: %s",
                floorplan_id,
                analysis_result.id,
                str(e),
            )
            # Decide whether to continue processing others or fail the whole batch
            # For now, log and continue

    logger.info(
        "Finished processing 'creation' task for AnalysisResult %s. Processed floorplans: %s",
        analysis_result.id,
        processed_floorplan_ids,
    )
    return {
        "message": "Webhook creation processing completed",
        "analysis_id": analysis_result.id,
        "processed_floorplan_ids": list(processed_floorplan_ids),
    }


def _handle_update_task(analysis_data):
    """Handles the 'update' task logic."""
    user_id = analysis_data["user_id"]  # Not strictly needed if floorplan_id is the key
    property_id = analysis_data[
        "property_id"
    ]  # Not strictly needed if floorplan_id is the key
    output_data = analysis_data["output_data"]

    if not isinstance(output_data, dict):
        logger.error(
            "Webhook 'update' task expected dict for output_data, got %s",
            type(output_data),
        )
        return {"error": "Invalid output_data format for update task."}

    floorplan_id = output_data.get("floorplan_id")
    if not floorplan_id:
        logger.error("Missing floorplan_id in update payload: %s", output_data)
        return {"error": "Missing floorplan_id in update payload"}

    try:
        # Find the existing FloorPlan and its AnalysisResult
        # Use select_related for efficiency
        floorplan = FloorPlan.objects.select_related("analysis_result").get(
            floorplan_id=floorplan_id
        )
        analysis_result = floorplan.analysis_result

        # Log association check
        if (
            analysis_result.user_id != user_id
            or analysis_result.property_id != property_id
        ):
            logger.warning(
                "Mismatch between update payload identifiers (user: %s, property: %s) and existing FloorPlan's AnalysisResult (user: %s, property: %s) for floorplan_id %s. Proceeding with update based on floorplan_id.",
                user_id,
                property_id,
                analysis_result.user_id,
                analysis_result.property_id,
                floorplan_id,
            )

        logger.info(
            "Processing update for existing FloorPlan ID %s (AnalysisResult ID %s)",
            floorplan_id,
            analysis_result.id,
        )
        _process_single_floorplan_data(output_data, analysis_result, is_update=True)

    except FloorPlan.DoesNotExist:
        logger.error("FloorPlan with id '%s' does not exist for update.", floorplan_id)
        return {"error": f"FloorPlan with id {floorplan_id} not found for update."}
    except Exception as e:
        logger.exception(
            "Error during update task for floorplan_id '%s': %s", floorplan_id, str(e)
        )
        return {"error": f"Failed to process update for floorplan {floorplan_id}."}

    logger.info("Finished processing 'update' task for floorplan_id %s.", floorplan_id)
    return {
        "message": "Floor update processing completed",
        "floorplan_id": floorplan_id,
        "analysis_id": analysis_result.id,
    }


def _process_single_floorplan_data(item_data, analysis_result, is_update=False):
    """
    Processes the data for a single floorplan (used by both creation and update).
    Handles FloorPlan, AllFloorsData, PlanFloor, CSVs, TotalArea, and Backup.
    """
    floorplan_id = item_data.get("floorplan_id")
    original_url = item_data.get("original_url")
    all_floors_item = item_data.get(
        "all_floors"
    )  # This is the dict for AllFloorsData URLs etc.
    floors_list = item_data.get("floors", [])  # This is the list for PlanFloor data

    if not floorplan_id or not all_floors_item:
        logger.warning(
            "Skipping floorplan item due to missing floorplan_id or all_floors data: %s",
            item_data,
        )
        # In an update, we might already have the floorplan object, but still need all_floors_item
        raise ValueError(
            "Missing essential data (floorplan_id or all_floors) in item payload."
        )

    # 1. Update or Create FloorPlan
    floorplan_defaults = {}
    if original_url:
        floorplan_defaults["original_url"] = original_url

    floorplan, fp_created = FloorPlan.objects.update_or_create(
        analysis_result=analysis_result,
        floorplan_id=floorplan_id,
        defaults=floorplan_defaults,
    )
    action_fp = "Created" if fp_created else "Updated"
    logger.info("%s FloorPlan with id=%s", action_fp, floorplan_id)

    # 2. Update or Create AllFloorsData
    all_floors_defaults = {
        "json_file_url": all_floors_item.get("json_file_url"),
        "csv_url": all_floors_item.get("csv_url"),  # The main all_floors.csv URL
        "total_area_csv_url": all_floors_item.get("total_area_csv_url"),
        "image_labelme_side_by_side_url": all_floors_item.get(
            "image_labelme_side_by_side_url"
        ),
        "notes": all_floors_item.get("notes", ""),
    }
    # Remove keys with None values if you don't want update_or_create to set them to NULL
    all_floors_defaults = {
        k: v for k, v in all_floors_defaults.items() if v is not None
    }

    all_floors_data, afd_created = AllFloorsData.objects.update_or_create(
        floor_plan=floorplan,
        defaults=all_floors_defaults,
    )
    action_afd = "Created" if afd_created else "Updated"
    logger.info("%s AllFloorsData for floorplan_id=%s", action_afd, floorplan_id)

    # 3. Update or Create PlanFloors (handle deletions)
    _update_plan_floors(floorplan, floors_list)

    # 4. Process the main CSV (all_floors.csv) -> Structured data + Raw Rows
    _process_main_csv(all_floors_data)

    # 5. Process the total_area.csv -> TotalAreaData model
    _process_total_area_csv(all_floors_data)

    # 6. Backup the processed state
    _perform_backup(floorplan)


def _update_plan_floors(floorplan, floors_list_data):
    """Updates PlanFloor entries based on the provided list, deleting orphans."""
    existing_plan_floor_names = set(
        floorplan.plan_floors.values_list("floor", flat=True)
    )
    current_plan_floor_names = set()

    for floor_data in floors_list_data:
        floor_name = floor_data.get("floor")
        if not floor_name:
            logger.warning(
                "Skipping plan floor item due to missing floor name for floorplan %s: %s",
                floorplan.floorplan_id,
                floor_data,
            )
            continue
        current_plan_floor_names.add(floor_name)

        plan_floor_defaults = {
            "label_me_url": floor_data.get("label_me_url"),
            "json_file_url": floor_data.get("json_file_url"),
            "image_url": floor_data.get("image_url"),
            "labelme_image_url": floor_data.get("labelme_image_url"),
            "csv_url": floor_data.get("csv_url"),  # Floor-specific CSV if provided
            "image_side_by_side_url": floor_data.get("image_side_by_side_url"),
        }
        # Remove None values if needed
        plan_floor_defaults = {
            k: v for k, v in plan_floor_defaults.items() if v is not None
        }

        pf, pf_created = PlanFloor.objects.update_or_create(
            floor_plan=floorplan,
            floor=floor_name,
            defaults=plan_floor_defaults,
        )
        action_pf = "Created" if pf_created else "Updated"
        # logger.debug("%s PlanFloor for floor=%s, floorplan=%s", action_pf, floor_name, floorplan.floorplan_id) # Less verbose logging

    # Delete PlanFloors that are no longer present
    floors_to_remove = existing_plan_floor_names - current_plan_floor_names
    if floors_to_remove:
        logger.info(
            "Removing old PlanFloors for floorplan %s not in new data: %s",
            floorplan.floorplan_id,
            floors_to_remove,
        )
        floorplan.plan_floors.filter(floor__in=floors_to_remove).delete()


def _download_csv_content(csv_url, context_msg):
    """Downloads CSV content from a URL, handles errors."""
    if not csv_url:
        logger.warning("No CSV URL provided for %s.", context_msg)
        return None
    try:
        logger.info("Downloading CSV for %s from %s", context_msg, csv_url)
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.Timeout:
        logger.error("Timeout downloading CSV for %s from %s", context_msg, csv_url)
        return None
    except requests.RequestException as e:
        logger.error(
            "Failed to download CSV for %s from %s: %s", context_msg, csv_url, str(e)
        )
        return None


def _process_main_csv(all_floors_data):
    """Downloads and processes the main all_floors.csv."""
    csv_url = all_floors_data.csv_url
    context_msg = f"main CSV (all_floors) for AllFloorsData ID {all_floors_data.id}"
    csv_content = _download_csv_content(csv_url, context_msg)

    if csv_content:
        try:
            csv_file = io.StringIO(csv_content)
            # Important: Handle potential BOM (Byte Order Mark) if CSV comes from Excel/Windows
            # Peek at the first few bytes
            header = csv_file.readline()
            if header.startswith("\ufeff"):
                header = header[1:]  # Remove BOM
            csv_file.seek(0)  # Reset pointer
            if header.startswith("\ufeff"):
                # Re-create StringIO without BOM if DictReader struggles
                csv_file = io.StringIO(
                    csv_content.decode("utf-8-sig")
                )  # More robust BOM handling

            reader = csv.DictReader(csv_file)
            rows = list(
                reader
            )  # Read all rows into memory to allow multiple passes if needed

            # 1. Process structured data (CsvFloor, CsvRoom, etc.)
            process_structured_csv_data(rows, all_floors_data)

            # 2. Process raw rows (AllFloorsCsvRawRow)
            process_raw_csv_rows(
                rows, all_floors_data, reader.fieldnames
            )  # Pass fieldnames

            logger.info("Main CSV processed successfully for %s", context_msg)

        except Exception as e:
            logger.exception(
                "Error processing main CSV content for %s: %s", context_msg, str(e)
            )
            # Decide if existing CSV data should be cleared or kept on error
            # Clearing might be safer to avoid stale data:
            # logger.warning("Clearing existing structured and raw CSV data due to processing error for %s", context_msg)
            all_floors_data.csv_floors.all().delete()  # Cascade deletes rooms etc.
            all_floors_data.all_floors_raw_rows.all().delete()

    else:
        logger.warning(
            "No main CSV content to process for %s. Clearing existing data.",
            context_msg,
        )
        # If the URL was present but download failed, or URL is now null, clear old data
        all_floors_data.csv_floors.all().delete()  # Cascade deletes rooms etc.
        all_floors_data.all_floors_raw_rows.all().delete()


def process_structured_csv_data(rows, all_floors_data):
    """
    Processes CSV rows into structured models (CsvFloor, CsvRoom, etc.).
    Uses update_or_create and handles deletion of orphans.
    Accepts a list of row dictionaries.
    """
    processed_floor_names = set()
    processed_room_ids_by_floor = {}  # {floor_name: {room_id1, room_id2, ...}}
    floor_cache = {}

    for i, row in enumerate(rows):
        # --- Data Extraction and Validation ---
        floor_name = safe_string(row.get("Floor_Name"))  # Use helper
        room_id_str = row.get("Room_id")

        if floor_name == "unknown":
            floor_name = f"unknown_{i}"  # Or skip row? Decide policy. Assuming 'unknown' is valid.
            logger.debug(
                "Row has 'unknown' Floor_Name, assigning unique name: '%s'. Row: %s",
                floor_name,
                row,  # Consider logging less verbosely
            )
        elif not floor_name:  # Handle empty floor name if necessary
            floor_name = "unspecified_floor"  # Or "unknown_floor"
            # logger.warning("CSV row has missing or empty Floor_Name. Row: %s", row)
            logger.debug(
                "Row has blank/None Floor_Name, assigning default: '%s'. Row: %s",
                floor_name,
                row,  # Consider logging less verbosely
            )
            # continue # Or skip if floor name is essential

        if not room_id_str:
            logger.warning(
                "Skipping CSV row for floor '%s' due to missing Room_id: %s",
                floor_name,
                row,
            )
            continue

        # Use safe_float for Room_id as model field is FloatField
        room_id = safe_float(room_id_str)
        if room_id is None:
            logger.warning(
                "Skipping CSV row for floor '%s' due to invalid Room_id format '%s': %s",
                floor_name,
                room_id_str,
                row,
            )
            continue

        # --- Track processed items ---
        processed_floor_names.add(floor_name)
        processed_room_ids_by_floor.setdefault(floor_name, set()).add(room_id)

        # --- Process CsvFloor ---
        if floor_name not in floor_cache:
            floor, f_created = CsvFloor.objects.update_or_create(
                all_floors_data=all_floors_data,
                floor_name=floor_name,
                defaults={
                    "calculated_total_area_metric": safe_float(
                        row.get("Calculated Floor Total Sq Area Metric")
                    ),
                    "calculated_total_area_imperial": safe_float(
                        row.get("Calculated Floor Total Sq Area Imperial")
                    ),
                },
            )
            floor_cache[floor_name] = floor
            # logger.debug("%s CsvFloor: %s", "Created" if f_created else "Updated", floor_name)
        else:
            floor = floor_cache[floor_name]

        # --- Process CsvRoom ---
        room_defaults = {
            "room_name": safe_string(row.get("Room_Name")),
            "is_segment": safe_string(row.get("is_segment")),
            "no_of_doors": safe_float(row.get("No_of_door")),  # Match CSV header case
            "no_of_windows": safe_float(
                row.get("No_of_window")
            ),  # Match CSV header case
            "no_of_room_points": safe_float(row.get("No_of_room_points")),
        }
        room, r_created = CsvRoom.objects.update_or_create(
            floor=floor,
            room_id=room_id,
            defaults=room_defaults,
        )
        # logger.debug("%s CsvRoom: %s (ID: %s)", "Created" if r_created else "Updated", room_defaults['room_name'], room_id)

        # --- Process Related OneToOne Fields (PixelData, Dimensions, Scaling) ---
        _update_or_create_room_details(room, row)

    # --- Clean up old structured data ---
    # Delete CsvFloors not in this CSV run
    floors_to_delete = all_floors_data.csv_floors.exclude(
        floor_name__in=processed_floor_names
    )
    if floors_to_delete.exists():
        deleted_floor_names = list(
            floors_to_delete.values_list("floor_name", flat=True)
        )
        logger.info(
            "Deleting %d CsvFloors (and related rooms) for AllFloorsData %d no longer present in CSV: %s",
            floors_to_delete.count(),
            all_floors_data.id,
            deleted_floor_names,
        )
        floors_to_delete.delete()  # Cascade should handle rooms

    # Delete CsvRooms within processed floors that were not in this CSV run
    for floor_name, processed_room_ids in processed_room_ids_by_floor.items():
        if floor_name in floor_cache:
            csv_floor = floor_cache[floor_name]
            rooms_to_delete = csv_floor.rooms.exclude(room_id__in=processed_room_ids)
            if rooms_to_delete.exists():
                deleted_room_ids = list(
                    rooms_to_delete.values_list("room_id", flat=True)
                )
                logger.info(
                    "Deleting %d CsvRooms for floor '%s' (AllFloorsData %d) no longer present in CSV: %s",
                    rooms_to_delete.count(),
                    floor_name,
                    all_floors_data.id,
                    deleted_room_ids,
                )
                rooms_to_delete.delete()  # Cascade handles related details

    logger.info(
        "Structured CSV data processing finished for AllFloorsData id=%s",
        all_floors_data.id,
    )


def _update_or_create_room_details(room, row_data):
    """Helper to update/create related OneToOne room details."""

    # --- Pixel Data ---
    pixel_defaults = {
        "min_x_pixels": safe_float(row_data.get("Min X Pixels")),
        "min_y_pixels": safe_float(row_data.get("Min Y Pixels")),
        "max_x_pixels": safe_float(row_data.get("Max X Pixels")),
        "max_y_pixels": safe_float(row_data.get("Max Y Pixels")),
        "max_area_pixels": safe_float(row_data.get("Max Area Pixels")),
        "actual_area_pixels": safe_float(row_data.get("Actual Area Pixels")),
        "pixel_ratio": safe_float(row_data.get("Pixel ratio")),
    }
    if any(v is not None for v in pixel_defaults.values()):
        CsvRoomPixelData.objects.update_or_create(room=room, defaults=pixel_defaults)
    else:
        CsvRoomPixelData.objects.filter(room=room).delete()  # Delete if no data

    # --- Dimensions ---
    dimension_defaults = {
        "dimensions_imperial": safe_dimension(row_data.get("dimensions_imperial")),
        "dimensions_metric": safe_dimension(row_data.get("dimensions_metric")),
        "max_area_metric": safe_float(row_data.get("Max Area Metric")),
        "max_area_imperial": safe_float(row_data.get("Max Area Imperial")),
        "calculated_sq_area_metric": safe_float(
            row_data.get("Calculated Sq Area Metric")
        ),
        "calculated_area_imperial": safe_float(
            row_data.get("calculated_area_imperial")
        ),  # Lowercase 'c' in header
    }
    if any(v is not None for v in dimension_defaults.values()):
        CsvRoomDimensions.objects.update_or_create(
            room=room, defaults=dimension_defaults
        )
    else:
        CsvRoomDimensions.objects.filter(room=room).delete()

    # --- Scaling Factors ---
    scaling_defaults = {
        "scale_metric": safe_float(row_data.get("Scale Metric")),
        "scale_imperial": safe_float(row_data.get("Scale Imperial")),
    }
    if any(v is not None for v in scaling_defaults.values()):
        CsvRoomScalingFactors.objects.update_or_create(
            room=room, defaults=scaling_defaults
        )
    else:
        CsvRoomScalingFactors.objects.filter(room=room).delete()


def process_raw_csv_rows(rows, all_floors_data, fieldnames):
    """
    Deletes existing raw rows for the AllFloorsData instance
    and bulk creates new AllFloorsCsvRawRow objects from the provided rows.
    """
    logger.info(
        "Processing raw CSV rows for AllFloorsData ID %d...", all_floors_data.id
    )

    # 1. Delete existing raw rows for this specific AllFloorsData instance
    count, _ = all_floors_data.all_floors_raw_rows.all().delete()
    if count > 0:
        logger.info(
            "Deleted %d existing raw CSV rows for AllFloorsData ID %d.",
            count,
            all_floors_data.id,
        )

    # 2. Prepare new raw row objects for bulk creation
    raw_rows_to_create = []
    for row_dict in rows:
        # Map CSV headers (keys in row_dict) to model fields
        # Be careful with case sensitivity and potential mismatches
        # Use safe conversion functions
        raw_row_instance = AllFloorsCsvRawRow(
            all_floors_data=all_floors_data,
            # Map fields, using .get() and safe helpers
            floor_name=safe_string(row_dict.get("Floor_Name")),
            room_name=safe_string(row_dict.get("Room_Name")),
            is_segment=safe_string(row_dict.get("is_segment")),
            room_id=safe_float(row_dict.get("Room_id")),
            no_of_door=safe_float(
                row_dict.get("No_of_door")
            ),  # Model field name matches CSV? Check model definition
            no_of_window=safe_float(
                row_dict.get("No_of_window")
            ),  # Check model definition
            no_of_room_points=safe_float(row_dict.get("No_of_room_points")),
            min_x_pixels=safe_float(
                row_dict.get("Min X Pixels")
            ),  # Check model field vs db_column
            min_y_pixels=safe_float(row_dict.get("Min Y Pixels")),
            max_x_pixels=safe_float(row_dict.get("Max X Pixels")),
            max_y_pixels=safe_float(row_dict.get("Max Y Pixels")),
            dimensions_imperial=safe_dimension(row_dict.get("dimensions_imperial")),
            dimensions_metric=safe_dimension(row_dict.get("dimensions_metric")),
            max_area_metric=safe_float(row_dict.get("Max Area Metric")),
            max_area_imperial=safe_float(row_dict.get("Max Area Imperial")),
            max_area_pixels=safe_float(row_dict.get("Max Area Pixels")),
            actual_area_pixels=safe_float(row_dict.get("Actual Area Pixels")),
            pixel_ratio=safe_float(row_dict.get("Pixel ratio")),
            scale_metric=safe_float(row_dict.get("Scale Metric")),
            scale_imperial=safe_float(row_dict.get("Scale Imperial")),
            calculated_sq_area_metric=safe_float(
                row_dict.get("Calculated Sq Area Metric")
            ),
            calculated_floor_total_sq_area_metric=safe_float(
                row_dict.get("Calculated Floor Total Sq Area Metric")
            ),
            calculated_area_imperial=safe_float(
                row_dict.get("calculated_area_imperial")
            ),  # Lowercase 'c'
            calculated_floor_total_sq_area_imperial=safe_float(
                row_dict.get("Calculated Floor Total Sq Area Imperial")
            ),
            # Add any other columns present in CSV and model (e.g., 0, 1, 2... if they exist)
            # Example for columns named '0', '1', etc. if they exist in fieldnames:
            # **{fieldname: safe_string(row_dict.get(fieldname)) for fieldname in fieldnames if fieldname.isdigit()}
        )
        # --- IMPORTANT: Double check model field names against CSV headers and `db_column` usage ---
        # The mapping above assumes model field names directly match the keys after safe conversion.
        # If `db_column` is used extensively, mapping needs care. E.g., if model field is `min_x`
        # but `db_column='min_x_pixels_csv'` and CSV header is 'Min X Pixels', the mapping is:
        # min_x=safe_float(row_dict.get("Min X Pixels"))

        raw_rows_to_create.append(raw_row_instance)

    # 3. Bulk create the new rows
    if raw_rows_to_create:
        try:
            created_rows = AllFloorsCsvRawRow.objects.bulk_create(raw_rows_to_create)
            logger.info(
                "Successfully created %d new raw CSV rows for AllFloorsData ID %d.",
                len(created_rows),
                all_floors_data.id,
            )
        except Exception as e:
            logger.exception(
                "Error during bulk creation of raw CSV rows for AllFloorsData ID %d: %s",
                all_floors_data.id,
                str(e),
            )
            # Consider what state the DB is in - transaction atomicity helps here.
    else:
        logger.info(
            "No raw CSV rows to create for AllFloorsData ID %d.", all_floors_data.id
        )


def _process_total_area_csv(all_floors_data):
    """Downloads and processes the total_area.csv."""
    total_area_csv_url = all_floors_data.total_area_csv_url
    context_msg = f"total_area.csv for AllFloorsData ID {all_floors_data.id}"
    csv_content = _download_csv_content(total_area_csv_url, context_msg)
    processed_area_names = set()

    if csv_content:
        try:
            csv_file = io.StringIO(csv_content)
            # Handle BOM if necessary (similar to main CSV)
            header = csv_file.readline()
            if header.startswith("\ufeff"):
                header = header[1:]
            csv_file.seek(0)
            if header.startswith("\ufeff"):
                csv_file = io.StringIO(csv_content.decode("utf-8-sig"))

            reader = csv.DictReader(csv_file)

            for row in reader:
                area_name = safe_string(row.get("Area Name"))  # Use helper
                if not area_name:
                    logger.warning(
                        "Skipping total_area.csv row due to missing Area Name for %s: %s",
                        context_msg,
                        row,
                    )
                    continue
                processed_area_names.add(area_name)

                defaults = {
                    # Map all columns using safe helpers
                    "square_meters": safe_float(row.get("Square Meters")),
                    "square_feet": safe_float(row.get("Square Feet")),
                    "total_floors": safe_int(row.get("Total Floors")),
                    "total_named_rooms": safe_int(row.get("Total Named Rooms")),
                    "total_segments": safe_int(row.get("Total Segments")),
                    "total_points": safe_int(row.get("Total Points")),
                    "total_objects": safe_int(row.get("Total Objects")),
                    "total_door_objects": safe_int(row.get("Total Door Objects")),
                    "total_window_objects": safe_int(row.get("Total Window Objects")),
                    "total_stair_objects": safe_int(row.get("Total Stair Objects")),
                    "list_of_objects": safe_string(row.get("List of Objects")),
                    "total_actual_pixels": safe_float(row.get("Total Pixels")),
                    "metric_scale": safe_float(row.get("Metric Scale")),
                    "imperial_scale": safe_float(row.get("Imperial Scale")),
                    "input_image_tokens": safe_int(row.get("Input Image Tokens")),
                    "input_text_tokens": safe_int(row.get("Input Text Tokens")),
                    "output_text_tokens": safe_int(row.get("Output Text Tokens")),
                }

                ta_data, ta_created = TotalAreaData.objects.update_or_create(
                    all_floors_data=all_floors_data,
                    area_name=area_name,
                    defaults=defaults,
                )
                # logger.debug("%s TotalAreaData for Area Name: %s", "Created" if ta_created else "Updated", area_name)

            # Delete stale TotalAreaData rows for this AllFloorsData
            stale_total_area_data = all_floors_data.total_area_data.exclude(
                area_name__in=processed_area_names
            )
            if stale_total_area_data.exists():
                deleted_area_names = list(
                    stale_total_area_data.values_list("area_name", flat=True)
                )
                logger.info(
                    "Deleting %d stale TotalAreaData rows for %s: %s",
                    stale_total_area_data.count(),
                    context_msg,
                    deleted_area_names,
                )
                stale_total_area_data.delete()

            logger.info("Total Area CSV processed successfully for %s", context_msg)

        except Exception as e:
            logger.exception(
                "Error processing total_area.csv content for %s: %s",
                context_msg,
                str(e),
            )
            # Decide on error handling - clear existing data?
            logger.warning(
                "Clearing existing TotalAreaData due to processing error for %s",
                context_msg,
            )
            all_floors_data.total_area_data.all().delete()

    else:
        logger.warning(
            "No total_area.csv content to process for %s. Clearing existing data.",
            context_msg,
        )
        # If URL/content missing, clear old data
        all_floors_data.total_area_data.all().delete()


def _perform_backup(floorplan):
    """Calls the backup utility function, handling potential errors."""
    try:
        logger.info("Attempting backup for floorplan_id=%s", floorplan.floorplan_id)
        backup_floorplan(
            floorplan
        )  # Assumes backup_floorplan handles its own logging on success/failure
        logger.info("Backup call completed for floorplan_id=%s", floorplan.floorplan_id)
    except Exception as e:
        # Log the error but don't let backup failure stop the main process
        logger.exception(
            "Error during backup attempt for floorplan_id %s: %s",
            floorplan.floorplan_id,
            str(e),
        )
