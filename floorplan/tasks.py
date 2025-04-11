# floorplan/tasks.py

import csv
import io

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F  # Import F object for atomic updates

from floorplan.models import (
    AllFloorsCsvData,
    AllFloorsData,
    CsvFloor,
    CsvRoom,
    CsvRoomDimensions,
    CsvRoomPixelData,
    CsvRoomScalingFactors,
    FloorPlan,
    FloorPlanAnalysisResult,
    PlanFloor,
    TotalAreasCsvData,
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
        # Use float conversion first to handle "5.0" etc.
        return int(float(value))
    except (ValueError, TypeError):
        return None


def safe_dimension(value):
    """Returns the value if it's a valid dimension string, else None."""
    if isinstance(value, str):
        value = value.strip()
        if value.lower() in INVALID_DIMENSION_VALUES:
            return None
    elif value in INVALID_DIMENSION_VALUES:
        return None
    return value


def safe_string(value):
    """Returns the stripped string value, or None if the input is None or results in empty string."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None  # Treat empty string as None after strip
    elif value is None:  # Handle explicit None
        return None
    # If it's not a string or None, try converting to string (e.g., numbers)
    try:
        str_val = str(value).strip()
        return str_val if str_val else None
    except:
        return None


@shared_task(bind=True)
def process_floorplan_analysis(self, user_id, property_id, floorplans):
    """
    Task to initiate the analysis process via the analyzer API.
    Calculates hash IDs before the call and uses them as floorplan IDs in the payload.
    """
    logger.info(
        "Starting floorplan analysis task for user_id=%s, property_id=%s",
        user_id,
        property_id,
    )
    webhook_url = getattr(
        settings,
        "FLOORPLAN_WEBHOOK_URL",
        "https://1ab9-41-76-192-17.ngrok-free.app/api/floorplan/webhook/",
    )
    # webhook_url = "https://1ab9-41-76-192-17.ngrok-free.app/api/floorplan/webhook/"
    analyzer_url = getattr(settings, "FLOORPLAN_ANALYZER_URL", None)

    if not webhook_url or not analyzer_url:
        logger.error(
            "Missing FLOORPLAN_WEBHOOK_URL or FLOORPLAN_ANALYZER_URL in settings."
        )
        return {"error": "Server configuration error: Missing required URLs."}

    # --- Generate Hashes and Build Payload ---
    hashed_floorplans_payload = {}
    skipped_floorplans = []  # Keep track of floorplans skipped due to hashing errors

    if not isinstance(floorplans, dict):
        logger.error("Invalid 'floorplans' input format. Expected a dictionary.")
        return {"error": "Invalid floorplans format."}

    # Ensure user_id and property_id are strings and not empty for hashing
    str_user_id = str(user_id).strip()
    str_property_id = str(property_id).strip()
    if not str_user_id or not str_property_id:
        logger.error("User ID and Property ID cannot be empty for hashing.")
        return {"error": "User ID and Property ID cannot be empty."}

    for original_key, fp_data in floorplans.items():
        if not isinstance(fp_data, dict) or "url" not in fp_data:
            logger.warning(
                f"Skipping floorplan item with key '{original_key}' due to invalid format or missing URL: {fp_data}"
            )
            skipped_floorplans.append(original_key)
            continue

        original_url = fp_data.get("url")
        if (
            not original_url
            or not isinstance(original_url, str)
            or not original_url.strip()
        ):
            logger.warning(
                f"Skipping floorplan item with key '{original_key}' due to invalid URL: {original_url}"
            )
            skipped_floorplans.append(original_key)
            continue

        original_url = original_url.strip()

        try:
            stable_hash_id = FloorPlan.generate_hash_id(
                property_id=str_property_id, user_id=str_user_id, url=original_url
            )
            # Payload for API uses hash as the key
            hashed_floorplans_payload[stable_hash_id] = {
                "url": original_url,
                "notes": fp_data.get("notes", ""),  # Include notes if provided
            }
            logger.info(
                f"Generated hash '{stable_hash_id}' for URL '{original_url}' (Original key: '{original_key}')"
            )
        except ValueError as e:
            logger.error(
                f"Failed to generate hash for URL '{original_url}' (Original key: '{original_key}'): {e}. Skipping this floorplan."
            )
            skipped_floorplans.append(original_key)
        except Exception as e:
            logger.exception(
                f"Unexpected error generating hash for URL '{original_url}' (Original key: '{original_key}'): {e}. Skipping."
            )
            skipped_floorplans.append(original_key)

    if not hashed_floorplans_payload:
        logger.error(
            "No valid floorplans could be processed or hashed for user_id=%s, property_id=%s. Aborting API call.",
            user_id,
            property_id,
        )
        return {"error": "No valid floorplans to process."}

    # --- Construct Final Payload ---
    payload = {
        "webhook_url": webhook_url,
        "user_id": user_id,
        "property_id": property_id,
        "floorplans": hashed_floorplans_payload,  # Use the dict with hashes as keys
    }

    # --- Call Analyzer API ---
    try:
        logger.info(
            "Calling analyzer API at %s with %d floorplans (hashes as IDs). Payload snippet: %s",
            analyzer_url,
            len(hashed_floorplans_payload),
            str(payload)[:500] + "...",  # Log snippet, avoid huge logs
        )
        response = requests.post(analyzer_url, json=payload, timeout=60)  # Add timeout
        response.raise_for_status()
        logger.info("Analyzer API call successful, analysis initiated.")
        if skipped_floorplans:
            logger.warning(
                f"API call initiated, but {len(skipped_floorplans)} floorplans were skipped due to errors: {skipped_floorplans}"
            )

    except requests.Timeout:
        logger.error("Timeout calling analyzer API at %s", analyzer_url)
        raise self.retry(countdown=60, max_retries=5)
    except requests.RequestException as e:
        status_code = getattr(e.response, "status_code", "N/A")
        response_text = getattr(e.response, "text", "N/A")
        logger.error(
            "Failed to call analyzer API: %s (Status: %s). Response: %s",
            str(e),
            status_code,
            response_text,
        )
        raise self.retry(exc=e, countdown=60, max_retries=5)
    except Exception as e:
        logger.exception(
            "Unexpected error during analyzer API call preparation/execution: %s", e
        )
        raise self.retry(exc=e, countdown=120, max_retries=3)

    logger.info(
        "Floorplan analysis initiation task completed for user_id=%s, property_id=%s",
        user_id,
        property_id,
    )
    return {"message": "Analysis initiated successfully"}


def _update_analysis_result_status(
    user_id,
    property_id,
    analysis_data,
    message_override=None,
    is_empty=False,
    error=None,
):
    """Helper to update the FloorPlanAnalysisResult status."""
    if message_override:
        message = message_override
    elif is_empty:
        message = analysis_data.get("message", "Extractor returned no floorplan data")
    elif error:
        message = f"Webhook processing error: {str(error)[:150]}"  # Limit error length
    else:
        message = analysis_data.get("message", "Analysis processed")

    try:
        analysis_result, created = FloorPlanAnalysisResult.objects.update_or_create(
            user_id=user_id,
            property_id=property_id,
            defaults={
                "message": message[:255],  # Truncate if necessary
                # If FloorPlanAnalysisResult has updated_at = auto_now=True, it's automatic
            },
        )
        action = "Created" if created else "Updated"
        logger.info(
            "%s FloorPlanAnalysisResult (ID: %s) for user %s, property %s with status: %s",
            action,
            analysis_result.id,
            user_id,
            property_id,
            message,
        )
        return analysis_result  # Return the instance
    except Exception as db_exc:
        logger.error(
            "Error updating FloorPlanAnalysisResult status for user %s, property %s: %s",
            user_id,
            property_id,
            db_exc,
        )
        return None


@shared_task(bind=True)
@transaction.atomic
def process_floorplan_webhook(self, analysis_data):
    """
    Processes the analysis payload sent to the webhook (entry point).
    Handles both 'creation' and 'update' task types, expecting a list in 'output_data'.
    Relies on the 'floorplan_id' in the payload being the pre-computed hash.
    Increments update_count on FloorPlan for 'update' tasks.
    """
    task_type = analysis_data.get("task")
    user_id = analysis_data.get("user_id")
    property_id = analysis_data.get("property_id")
    output_data = analysis_data.get("output_data")  # Extract output_data
    message = analysis_data.get("message", f"Webhook task '{task_type}' received")

    logger.info(
        "Processing webhook task '%s' for user '%s', property '%s'.",
        task_type,
        user_id,
        property_id,
    )

    # 1. Check base required fields
    base_required = {"task": task_type, "user_id": user_id, "property_id": property_id}
    missing_base = [k for k, v in base_required.items() if not v]
    if missing_base:
        error_msg = f"Missing required base fields in webhook payload: {missing_base}"
        logger.error(f"{error_msg}. Payload: {analysis_data}")
        # Attempt to update status even with missing fields if possible
        if user_id and property_id:
            _update_analysis_result_status(
                user_id, property_id, analysis_data, error=error_msg
            )
        return {"error": error_msg}

    # Validate task type
    if task_type not in ["creation", "update"]:
        error_msg = f"Unknown task type: {task_type}"
        logger.error(f"{error_msg}. Payload: {analysis_data}")
        _update_analysis_result_status(
            user_id, property_id, analysis_data, error=error_msg
        )
        return {"error": error_msg}

    # 2. Check if output_data exists and is a list
    if output_data is None:
        error_msg = "Missing required field 'output_data' in webhook payload"
        logger.error(f"{error_msg}. Payload: {analysis_data}")
        _update_analysis_result_status(
            user_id, property_id, analysis_data, error=error_msg
        )
        return {"error": error_msg}

    if not isinstance(output_data, list):
        error_msg = f"Invalid output_data type in webhook payload: expected list, got {type(output_data).__name__}"
        logger.error(f"{error_msg}. Payload: {analysis_data}")
        _update_analysis_result_status(
            user_id, property_id, analysis_data, error=error_msg
        )
        return {"error": error_msg}

    # 3. Handle EMPTY list case
    if not output_data:
        logger.warning(
            "Webhook received empty output_data list for user %s, property %s. Task type: '%s'. Assuming no floorplans processed/returned. Payload: %s",
            user_id,
            property_id,
            task_type,
            analysis_data,
        )
        _update_analysis_result_status(
            user_id, property_id, analysis_data, is_empty=True
        )
        return {
            "message": "Webhook processed successfully, but output_data list was empty."
        }

    logger.info(
        "Processing task '%s' with %d item(s) in output_data",
        task_type,
        len(output_data),
    )

    # --- Process Floorplan Data ---
    processed_stable_ids = set()
    errors_occurred = False
    analysis_result = None

    try:
        initial_message = message or f"Processing webhook task '{task_type}'..."
        # Get or create the overall analysis result record first
        analysis_result = _update_analysis_result_status(
            user_id, property_id, analysis_data, message_override=initial_message
        )
        if not analysis_result:
            # If we couldn't even get/create the analysis result, abort
            raise Exception("Failed to get or create FloorPlanAnalysisResult record.")

        # Process each floorplan item in the list
        for item_data in output_data:
            if not isinstance(item_data, dict):
                logger.warning(
                    "Skipping non-dict item in output_data list: %s", item_data
                )
                errors_occurred = True
                continue

            try:
                # Process this single floorplan's data, passing the task_type
                # to handle potential update count increment
                processed_fp_instance = _process_single_floorplan_data(
                    item_data, analysis_result, task_type, user_id, property_id
                )
                if processed_fp_instance:
                    processed_stable_ids.add(processed_fp_instance.floorplan_id)
                else:
                    # Error logged within _process_single_floorplan_data
                    errors_occurred = True
            except Exception as e:
                item_id = item_data.get("floorplan_id", "N/A")
                logger.exception(
                    "Error processing floorplan item (Hash ID: %s) during %s task for AnalysisResult %s: %s",
                    item_id,
                    task_type,
                    analysis_result.id,
                    str(e),
                )
                errors_occurred = True
                # Continue processing other items in the batch

        final_message = f"Webhook task '{task_type}' processing completed"
        if errors_occurred:
            final_message += " with errors"
            # Update analysis result status again if item processing had errors
            _update_analysis_result_status(
                user_id,
                property_id,
                analysis_data,
                error=f"Errors occurred processing some items in {task_type} task.",
            )
        else:
            _update_analysis_result_status(
                user_id, property_id, analysis_data, message_override=final_message
            )  # Update with success message

        logger.info(
            "Finished processing task '%s' for AnalysisResult %s. Processed floorplan IDs: %s",
            task_type,
            analysis_result.id,
            processed_stable_ids,
        )

        return {
            "message": final_message,
            "analysis_id": analysis_result.id,
            "processed_floorplan_ids": list(processed_stable_ids),
        }

    except Exception as e:
        logger.exception(
            "Unhandled error during webhook processing main loop for task '%s', user '%s', property '%s': %s",
            task_type,
            user_id,
            property_id,
            str(e),
        )
        # Update status if possible
        if user_id and property_id:
            _update_analysis_result_status(
                user_id, property_id, analysis_data, error=f"Unhandled error: {e}"
            )
        return {"error": f"Internal server error during webhook processing: {str(e)}"}


# Removed _handle_creation_task and _handle_update_task as they are merged into process_floorplan_webhook


def _process_single_floorplan_data(
    item_data, analysis_result, task_type, webhook_user_id, webhook_property_id
):
    """
    Processes the data for a single floorplan item received from the webhook.
    Uses the 'floorplan_id' (hash) and 'original_url' directly from the API response.
    Uses update_or_create for FloorPlan based on the received hash ID.
    Increments 'update_count' if task_type is 'update' and the record existed.
    Returns the processed FloorPlan instance or None on failure.
    """
    api_returned_hash_id = item_data.get("floorplan_id")
    api_returned_url = item_data.get("original_url")
    all_floors_item = item_data.get("all_floors")  # Dict for AllFloorsData URLs etc.
    floors_list = item_data.get("floors", [])  # List for PlanFloor data

    # --- Validation ---
    if (
        not api_returned_hash_id
        or not isinstance(api_returned_hash_id, str)
        or len(api_returned_hash_id) != 64
    ):
        logger.error(
            "Invalid or missing 'floorplan_id' (hash) received from API. Cannot process. Item data: %s",
            item_data,
        )
        return None
    if (
        not api_returned_url
        or not isinstance(api_returned_url, str)
        or not api_returned_url.strip()
    ):
        logger.error(
            "Invalid or missing 'original_url' received from API. Cannot process. Item data: %s",
            item_data,
        )
        return None
    if not all_floors_item or not isinstance(all_floors_item, dict):
        logger.warning(
            "Skipping floorplan item processing (Hash ID: %s) due to missing or invalid 'all_floors' data in webhook item: %s",
            api_returned_hash_id,
            item_data,
        )
        # Decide if this should be an error or just a warning. Returning None indicates failure for this item.
        return None

    # --- Assign IDs and URLs ---
    stable_floorplan_id = api_returned_hash_id
    source_url_for_db = api_returned_url.strip()

    # --- Optional Consistency Check ---
    try:
        str_webhook_user_id = str(webhook_user_id).strip()
        str_webhook_property_id = str(webhook_property_id).strip()
        if not str_webhook_user_id or not str_webhook_property_id:
            logger.error("Cannot verify hash: Webhook user_id or property_id is empty.")
        else:
            expected_hash = FloorPlan.generate_hash_id(
                property_id=str_webhook_property_id,
                user_id=str_webhook_user_id,
                url=source_url_for_db,
            )
            if expected_hash != stable_floorplan_id:
                logger.warning(
                    "Hash ID mismatch! API returned hash '%s' but calculated hash for URL '%s' is '%s'. Proceeding with API's hash.",
                    stable_floorplan_id,
                    source_url_for_db,
                    expected_hash,
                )
            else:
                logger.debug(
                    "API hash ID matches calculated hash for URL %s.", source_url_for_db
                )
    except ValueError as hash_exc:
        logger.error(
            "Failed to calculate verification hash for URL '%s': %s. Cannot verify API hash consistency.",
            source_url_for_db,
            hash_exc,
        )
        # Continue processing despite failed verification for now

    logger.info(
        f"Processing floorplan item (Hash ID: {stable_floorplan_id}, URL: {source_url_for_db})"
    )

    # 1. Update or Create FloorPlan using the STABLE HASH ID from API
    floorplan_defaults = {
        "analysis_result": analysis_result,
        "original_url": source_url_for_db,
        # updated_at is handled by TrackingModel/auto_now=True
        # update_count is handled below
    }
    try:
        floorplan, fp_created = FloorPlan.objects.update_or_create(
            floorplan_id=stable_floorplan_id, defaults=floorplan_defaults
        )
    except Exception as db_exc:
        logger.exception(
            "Database error during FloorPlan update_or_create for hash %s (URL: %s): %s",
            stable_floorplan_id,
            source_url_for_db,
            db_exc,
        )
        return None  # Indicate failure

    action_fp = "Created" if fp_created else "Updated"
    logger.info("%s FloorPlan with Stable ID (Hash)=%s", action_fp, stable_floorplan_id)

    # --- Increment Update Count if applicable ---
    if not fp_created and task_type == "update":
        try:
            # Perform atomic increment using F() object
            rows_updated = FloorPlan.objects.filter(pk=floorplan.pk).update(
                update_count=F("update_count") + 1
            )
            # Refresh the instance variable if needed, though not strictly necessary here
            # floorplan.refresh_from_db(fields=['update_count'])
            if rows_updated:
                logger.info(
                    "Incremented update_count for FloorPlan %s", stable_floorplan_id
                )
            else:
                logger.warning(
                    "Did not increment update_count (record possibly deleted?) for FloorPlan %s",
                    stable_floorplan_id,
                )
        except Exception as update_exc:
            logger.error(
                "Failed to increment update_count for FloorPlan %s: %s",
                stable_floorplan_id,
                update_exc,
            )
            # Continue processing other data, but log the error

    # 2. Update or Create AllFloorsData
    all_floors_data = None  # Initialize to None
    all_floors_defaults = {
        "json_file_url": all_floors_item.get("json_file_url"),
        "csv_url": all_floors_item.get("csv_url"),
        "total_area_csv_url": all_floors_item.get("total_area_csv_url"),
        "image_labelme_side_by_side_url": all_floors_item.get(
            "image_labelme_side_by_side_url"
        ),
        "notes": all_floors_item.get("notes", ""),
        # updated_at is handled by TrackingModel/auto_now=True
    }
    # Remove keys with None values to avoid overwriting existing data with None
    all_floors_defaults = {
        k: v for k, v in all_floors_defaults.items() if v is not None
    }

    if not all_floors_defaults:
        logger.warning(
            "No valid data provided for AllFloorsData for floorplan %s. Skipping update/create.",
            stable_floorplan_id,
        )
    else:
        try:
            all_floors_data, afd_created = AllFloorsData.objects.update_or_create(
                floor_plan=floorplan,
                defaults=all_floors_defaults,
            )
            action_afd = "Created" if afd_created else "Updated"
            logger.info(
                "%s AllFloorsData for Stable Floorplan ID=%s",
                action_afd,
                stable_floorplan_id,
            )
        except Exception as db_exc:
            logger.exception(
                "Database error during AllFloorsData update/create for floorplan %s: %s",
                stable_floorplan_id,
                db_exc,
            )
            # If AllFloorsData fails, we cannot process CSVs. Decide if this should halt backup too.
            # For now, log and proceed to PlanFloors, but skip CSVs.

    # 3. Update or Create PlanFloors (handle deletions)
    _update_plan_floors(floorplan, floors_list)

    # 4. Process CSVs only if AllFloorsData was successfully created/updated
    if all_floors_data:
        _process_main_csv(all_floors_data)
        _process_total_area_csv(all_floors_data)
    else:
        logger.warning(
            "Skipping CSV processing as AllFloorsData was not available for floorplan %s.",
            stable_floorplan_id,
        )

    # 6. Backup the processed state (consider if backup should run if CSVs failed)
    _perform_backup(floorplan)

    return floorplan  # Return the processed instance


def _update_plan_floors(floorplan, floors_list_data):
    """Updates PlanFloor entries based on the provided list, deleting orphans."""
    # Get existing floor names efficiently
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
            "csv_url": floor_data.get("csv_url"),
            "image_side_by_side_url": floor_data.get("image_side_by_side_url"),
            # updated_at is handled by TrackingModel/auto_now=True
        }
        # Only update fields that are actually provided in the payload
        plan_floor_defaults = {
            k: v for k, v in plan_floor_defaults.items() if v is not None
        }

        try:
            pf, pf_created = PlanFloor.objects.update_or_create(
                floor_plan=floorplan,
                floor=floor_name,
                defaults=plan_floor_defaults,
            )
            # action_pf = "Created" if pf_created else "Updated" # Less verbose logging
        except Exception as e:
            logger.error(
                "Error updating/creating PlanFloor '%s' for floorplan %s: %s",
                floor_name,
                floorplan.floorplan_id,
                e,
            )

    # Determine which floors need to be removed
    floors_to_remove = existing_plan_floor_names - current_plan_floor_names
    if floors_to_remove:
        logger.info(
            "Removing %d old PlanFloors for floorplan %s not in new data: %s",
            len(floors_to_remove),
            floorplan.floorplan_id,
            floors_to_remove,
        )
        deleted_count, _ = floorplan.plan_floors.filter(
            floor__in=floors_to_remove
        ).delete()
        logger.info("Deleted %d PlanFloor records.", deleted_count)


def _download_csv_content(csv_url, context_msg):
    """Downloads CSV content from a URL, handles errors."""
    if not csv_url:
        logger.warning("No CSV URL provided for %s.", context_msg)
        return None
    try:
        logger.info("Downloading CSV for %s from %s", context_msg, csv_url)
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()
        # Check content type? Or rely on processing errors?
        # if 'text/csv' not in response.headers.get('Content-Type', ''):
        #     logger.warning("Downloaded content for %s does not appear to be CSV. URL: %s", context_msg, csv_url)
        #     return None # Or try processing anyway
        return response.text
    except requests.Timeout:
        logger.error("Timeout downloading CSV for %s from %s", context_msg, csv_url)
        return None
    except requests.RequestException as e:
        status_code = getattr(e.response, "status_code", "N/A")
        logger.error(
            "Failed to download CSV for %s from %s: %s (Status: %s)",
            context_msg,
            csv_url,
            str(e),
            status_code,
        )
        return None


def _process_main_csv(all_floors_data):
    """Downloads and processes the main all_floors.csv."""
    csv_url = all_floors_data.csv_url
    context_msg = f"main CSV (all_floors) for AllFloorsData ID {all_floors_data.id} (FloorPlan: {all_floors_data.floor_plan.floorplan_id})"
    csv_content = _download_csv_content(csv_url, context_msg)

    if csv_content:
        try:
            # Detect and handle potential BOM (Byte Order Mark)
            if csv_content.startswith("\ufeff"):
                csv_file = io.StringIO(csv_content[1:])
                logger.debug("Removed BOM from main CSV content.")
            else:
                csv_file = io.StringIO(csv_content)

            # Validate header row if possible (check for expected columns)
            # reader = csv.reader(csv_file)
            # header = next(reader, None)
            # csv_file.seek(0) # Reset file pointer
            # if not header or 'Room_id' not in header: # Example check
            #      logger.error("Main CSV for %s is missing expected headers.", context_msg)
            #      return # Stop processing if header is invalid

            reader = csv.DictReader(csv_file)
            rows = list(reader)  # Read all rows into memory

            if not rows:
                logger.warning(
                    "Main CSV for %s is empty or contains only headers.", context_msg
                )
                # Clear existing data as the source is empty
                all_floors_data.csv_floors.all().delete()
                all_floors_data.all_floors_csv_data.all().delete()
                return

            process_structured_csv_data(rows, all_floors_data)
            process_raw_csv_rows(rows, all_floors_data, reader.fieldnames)

            logger.info("Main CSV processed successfully for %s", context_msg)

        except csv.Error as csv_e:
            logger.exception(
                "CSV parsing error processing main CSV content for %s: %s",
                context_msg,
                str(csv_e),
            )
            # Decide whether to clear data on parsing errors
        except Exception as e:
            logger.exception(
                "Unexpected error processing main CSV content for %s: %s",
                context_msg,
                str(e),
            )
            # Decide whether to clear data on general errors
    else:
        logger.warning(
            "No main CSV content downloaded for %s. Clearing potentially existing data.",
            context_msg,
        )
        all_floors_data.csv_floors.all().delete()
        all_floors_data.all_floors_csv_data.all().delete()


def process_structured_csv_data(rows, all_floors_data):
    """
    Processes CSV rows into structured models (CsvFloor, CsvRoom, etc.).
    Uses update_or_create and handles deletion of orphans.
    Uses 'unspecified_floor' for blank/unknown floor names.
    """
    processed_floor_names = set()
    # Use tuple (floor_name, room_id) as key to uniquely identify rooms across floors
    processed_room_keys = set()
    floor_cache = {}  # Cache CsvFloor instances by name

    for row_num, row in enumerate(rows, start=2):  # start=2 assuming header is row 1
        floor_name_raw = row.get("Floor_Name")
        floor_name = safe_string(floor_name_raw)

        if not floor_name or floor_name.lower() == "unknown":
            floor_name = "unspecified_floor"

        room_id_str = row.get("Room_id")
        room_id = safe_float(room_id_str)

        if room_id is None:
            logger.warning(
                "Skipping CSV row #%d for floor '%s' due to invalid/missing Room_id ('%s').",
                row_num,
                floor_name,
                room_id_str,
            )
            continue

        # Unique key for this room within this CSV
        room_key = (floor_name, room_id)
        processed_floor_names.add(floor_name)
        processed_room_keys.add(room_key)

        # --- Get or Create CsvFloor ---
        if floor_name not in floor_cache:
            try:
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
            except Exception as e:
                logger.error(
                    "Error getting/creating CsvFloor '%s' for AFD %d: %s",
                    floor_name,
                    all_floors_data.id,
                    e,
                )
                continue  # Skip this row if floor cannot be processed
        else:
            floor = floor_cache[floor_name]

        # --- Update or Create CsvRoom ---
        room_defaults = {
            "room_name": safe_string(row.get("Room_Name")),
            "is_segment": safe_string(row.get("is_segment")),
            "no_of_doors": safe_float(
                row.get("No_of_door")
            ),  # Ensure header names match exactly
            "no_of_windows": safe_float(row.get("No_of_window")),
            "no_of_room_points": safe_float(row.get("No_of_room_points")),
            # updated_at is handled by TrackingModel/auto_now=True
        }
        try:
            room, r_created = CsvRoom.objects.update_or_create(
                floor=floor,
                room_id=room_id,
                defaults=room_defaults,
            )
        except Exception as e:
            logger.error(
                "Error getting/creating CsvRoom ID %s for Floor '%s' (AFD %d): %s",
                room_id,
                floor_name,
                all_floors_data.id,
                e,
            )
            continue  # Skip room details if room cannot be processed

        # --- Update or Create related room details ---
        try:
            _update_or_create_room_details(room, row)
        except Exception as detail_e:
            logger.error(
                "Error processing details for CsvRoom ID %s (PK %d): %s",
                room_id,
                room.pk,
                detail_e,
            )
            # Continue to next row even if details fail

    # --- Clean up old structured data ---
    # Delete CsvFloors not present in the current CSV
    floors_to_delete = all_floors_data.csv_floors.exclude(
        floor_name__in=processed_floor_names
    )
    if floors_to_delete.exists():
        deleted_count_f, _ = floors_to_delete.delete()
        logger.info(
            "Deleted %d CsvFloors (and related rooms) for AllFloorsData %d no longer present in CSV.",
            deleted_count_f,
            all_floors_data.id,
        )

    # Delete CsvRooms within remaining floors that were not present in the current CSV
    for floor_name, floor_instance in floor_cache.items():
        # Get room_ids that were processed for *this specific floor*
        current_room_ids_for_floor = {
            key[1] for key in processed_room_keys if key[0] == floor_name
        }
        rooms_to_delete = floor_instance.rooms.exclude(
            room_id__in=current_room_ids_for_floor
        )
        if rooms_to_delete.exists():
            deleted_count_r, _ = rooms_to_delete.delete()
            logger.info(
                "Deleted %d CsvRooms for floor '%s' (AllFloorsData %d) no longer present in CSV.",
                deleted_count_r,
                floor_name,
                all_floors_data.id,
            )

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
        # updated_at is handled by TrackingModel/auto_now=True
    }
    pixel_defaults = {
        k: v for k, v in pixel_defaults.items() if v is not None
    }  # Keep only non-None values
    if pixel_defaults:  # Only process if there's actual data
        CsvRoomPixelData.objects.update_or_create(room=room, defaults=pixel_defaults)
    else:
        # If all values were None or missing, delete existing record if it exists
        deleted_count, _ = CsvRoomPixelData.objects.filter(room=room).delete()
        if deleted_count:
            logger.debug(
                "Deleted CsvRoomPixelData for room %d as all input values were None/missing.",
                room.id,
            )

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
            row_data.get("calculated_area_imperial")  # Check CSV header case
        ),
        # updated_at is handled by TrackingModel/auto_now=True
    }
    dimension_defaults = {k: v for k, v in dimension_defaults.items() if v is not None}
    if dimension_defaults:
        CsvRoomDimensions.objects.update_or_create(
            room=room, defaults=dimension_defaults
        )
    else:
        deleted_count, _ = CsvRoomDimensions.objects.filter(room=room).delete()
        if deleted_count:
            logger.debug(
                "Deleted CsvRoomDimensions for room %d as all input values were None/missing.",
                room.id,
            )

    # --- Scaling Factors ---
    scaling_defaults = {
        "scale_metric": safe_float(row_data.get("Scale Metric")),
        "scale_imperial": safe_float(row_data.get("Scale Imperial")),
        # updated_at is handled by TrackingModel/auto_now=True
    }
    scaling_defaults = {k: v for k, v in scaling_defaults.items() if v is not None}
    if scaling_defaults:
        CsvRoomScalingFactors.objects.update_or_create(
            room=room, defaults=scaling_defaults
        )
    else:
        deleted_count, _ = CsvRoomScalingFactors.objects.filter(room=room).delete()
        if deleted_count:
            logger.debug(
                "Deleted CsvRoomScalingFactors for room %d as all input values were None/missing.",
                room.id,
            )


def process_raw_csv_rows(rows, all_floors_data, fieldnames):
    """
    Deletes existing raw rows for the AllFloorsData instance
    and bulk creates new AllFloorsCsvData objects from the provided rows.
    """
    logger.info(
        "Processing raw CSV rows for AllFloorsData ID %d...", all_floors_data.id
    )

    # Delete existing raw rows first for a clean slate
    try:
        count, _ = all_floors_data.all_floors_csv_data.all().delete()
        if count > 0:
            logger.debug(
                "Deleted %d existing raw CSV rows for AllFloorsData ID %d.",
                count,
                all_floors_data.id,
            )
    except Exception as e:
        logger.error(
            "Error deleting existing raw CSV rows for AFD %d: %s", all_floors_data.id, e
        )
        # Decide if we should proceed without clearing? For now, let's stop.
        return

    raw_rows_to_create = []
    for row_num, row_dict in enumerate(rows, start=2):
        # Map ALL fields present in the model definition for AllFloorsCsvData
        # Use safe helpers for type consistency and handling bad data
        try:
            raw_row_instance = AllFloorsCsvData(
                all_floors_data=all_floors_data,  # Link instance for bulk create
                # Basic Info
                floor_name=safe_string(row_dict.get("Floor_Name")),
                room_name=safe_string(row_dict.get("Room_Name")),
                is_segment=safe_string(row_dict.get("is_segment")),
                room_id=safe_float(row_dict.get("Room_id")),
                # Counts
                no_of_door=safe_float(row_dict.get("No_of_door")),
                no_of_window=safe_float(row_dict.get("No_of_window")),
                no_of_room_points=safe_float(row_dict.get("No_of_room_points")),
                # Pixels
                min_x_pixels=safe_float(row_dict.get("Min X Pixels")),
                min_y_pixels=safe_float(row_dict.get("Min Y Pixels")),
                max_x_pixels=safe_float(row_dict.get("Max X Pixels")),
                max_y_pixels=safe_float(row_dict.get("Max Y Pixels")),
                max_area_pixels=safe_float(row_dict.get("Max Area Pixels")),
                actual_area_pixels=safe_float(row_dict.get("Actual Area Pixels")),
                pixel_ratio=safe_float(row_dict.get("Pixel ratio")),
                # Dimensions & Areas
                dimensions_imperial=safe_dimension(row_dict.get("dimensions_imperial")),
                dimensions_metric=safe_dimension(row_dict.get("dimensions_metric")),
                max_area_metric=safe_float(row_dict.get("Max Area Metric")),
                max_area_imperial=safe_float(row_dict.get("Max Area Imperial")),
                calculated_sq_area_metric=safe_float(
                    row_dict.get("Calculated Sq Area Metric")
                ),
                calculated_area_imperial=safe_float(
                    row_dict.get("calculated_area_imperial")  # Check case
                ),
                # Scales
                scale_metric=safe_float(row_dict.get("Scale Metric")),
                scale_imperial=safe_float(row_dict.get("Scale Imperial")),
                # Floor Totals (repeated per row)
                calculated_floor_total_sq_area_metric=safe_float(
                    row_dict.get("Calculated Floor Total Sq Area Metric")
                ),
                calculated_floor_total_sq_area_imperial=safe_float(
                    row_dict.get("Calculated Floor Total Sq Area Imperial")
                ),
                # created_at/updated_at are handled by TrackingModel
            )
            raw_rows_to_create.append(raw_row_instance)
        except Exception as e:
            logger.error(
                "Error preparing raw CSV row #%d for AFD %d: %s. Row data: %s",
                row_num,
                all_floors_data.id,
                e,
                row_dict,
            )
            # Skip this row but continue with others

    if raw_rows_to_create:
        try:
            # Use ignore_conflicts=False (default) unless duplicates are expected and okay
            created_rows = AllFloorsCsvData.objects.bulk_create(
                raw_rows_to_create, batch_size=500
            )  # Use batch_size
            logger.info(
                "Successfully created %d new raw CSV rows for AllFloorsData ID %d.",
                len(created_rows),
                all_floors_data.id,
            )
        except Exception as e:
            # This might indicate a larger DB issue or constraint violation
            logger.exception(
                "Error during bulk creation of raw CSV rows for AllFloorsData ID %d: %s",
                all_floors_data.id,
                str(e),
            )
    else:
        logger.info(
            "No valid raw CSV rows generated to create for AllFloorsData ID %d.",
            all_floors_data.id,
        )


def _process_total_area_csv(all_floors_data):
    """Downloads and processes the total_area.csv."""
    total_area_csv_url = all_floors_data.total_area_csv_url
    context_msg = f"total_area.csv for AllFloorsData ID {all_floors_data.id} (FloorPlan: {all_floors_data.floor_plan.floorplan_id})"
    csv_content = _download_csv_content(total_area_csv_url, context_msg)
    processed_area_names = set()

    if csv_content:
        try:
            # Handle BOM
            if csv_content.startswith("\ufeff"):
                csv_file = io.StringIO(csv_content[1:])
                logger.debug("Removed BOM from total_area CSV content.")
            else:
                csv_file = io.StringIO(csv_content)

            reader = csv.DictReader(csv_file)
            rows = list(reader)  # Read all rows

            if not rows:
                logger.warning(
                    "Total Area CSV for %s is empty or contains only headers.",
                    context_msg,
                )
                all_floors_data.total_areas_csv_data.all().delete()  # Clear existing
                return

            for row_num, row in enumerate(rows, start=2):
                area_name = safe_string(row.get("Area Name"))
                if not area_name:
                    logger.warning(
                        "Skipping total_area.csv row #%d due to missing Area Name for %s",
                        row_num,
                        context_msg,
                    )
                    continue
                processed_area_names.add(area_name)

                defaults = {
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
                    "total_actual_pixels": safe_float(
                        row.get("Total Actual Pixels")
                    ),  # Check header name
                    "metric_scale": safe_float(row.get("Metric Scale")),
                    "imperial_scale": safe_float(row.get("Imperial Scale")),
                    "input_image_tokens": safe_int(row.get("Input Image Tokens")),
                    "input_text_tokens": safe_int(row.get("Input Text Tokens")),
                    "output_text_tokens": safe_int(row.get("Output Text Tokens")),
                    # updated_at is handled by TrackingModel/auto_now=True
                }
                # Keep only non-None values for defaults
                defaults = {k: v for k, v in defaults.items() if v is not None}

                try:
                    # Use update_or_create to handle potential re-processing
                    ta_data, ta_created = TotalAreasCsvData.objects.update_or_create(
                        all_floors_data=all_floors_data,
                        area_name=area_name,
                        defaults=defaults,
                    )
                except Exception as e:
                    logger.error(
                        "Error updating/creating TotalAreasCsvData '%s' for AFD %d: %s",
                        area_name,
                        all_floors_data.id,
                        e,
                    )
                    # Continue to next row

            # Delete stale TotalAreasCsvData rows not present in the current CSV
            stale_total_areas_csv_data = all_floors_data.total_areas_csv_data.exclude(
                area_name__in=processed_area_names
            )
            if stale_total_areas_csv_data.exists():
                deleted_count, _ = stale_total_areas_csv_data.delete()
                logger.info(
                    "Deleted %d stale TotalAreasCsvData rows for %s.",
                    deleted_count,
                    context_msg,
                )

            logger.info("Total Area CSV processed successfully for %s", context_msg)

        except csv.Error as csv_e:
            logger.exception(
                "CSV parsing error processing total_area.csv content for %s: %s",
                context_msg,
                str(csv_e),
            )
        except Exception as e:
            logger.exception(
                "Error processing total_area.csv content for %s: %s",
                context_msg,
                str(e),
            )
            # Decide whether to clear data on errors
    else:
        logger.warning(
            "No total_area.csv content downloaded for %s. Clearing potentially existing data.",
            context_msg,
        )
        all_floors_data.total_areas_csv_data.all().delete()


def _perform_backup(floorplan):
    """Calls the backup utility function, handling potential errors."""
    try:
        if not floorplan or not floorplan.floorplan_id:
            logger.error("Backup skipped: Invalid floorplan object provided.")
            return

        logger.info("Attempting backup for floorplan_id=%s", floorplan.floorplan_id)
        # backup_floorplan should ideally handle the serialization itself
        backup_floorplan(floorplan)
        logger.info("Backup call completed for floorplan_id=%s", floorplan.floorplan_id)
    except Exception as e:
        # Log the full exception details
        logger.exception(
            "Error during backup attempt for floorplan_id %s: %s",
            getattr(floorplan, "floorplan_id", "N/A"),
            str(e),
        )
        # Do not re-raise here to allow main processing to finish,
        # but the error is logged. Consider adding specific monitoring for backup failures.
