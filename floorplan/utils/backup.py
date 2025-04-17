# floorplan/utils/backup.py
import requests
from django.conf import settings
from django.forms.models import model_to_dict

# Assuming you have your logger configured
from floorplan_service.config.logging_config import configure_logger

logger = configure_logger(__name__)


# --- Helper function to serialize for SDB ---
# This encapsulates the logic to create the payload expected by the SDB service
def serialize_floorplan_for_sdb(instance):
    """
    Serializes a FloorPlan instance and its related data into the structure
    expected by the CompletesdbFloorPlanSerializer in the sdb service.
    """
    if not instance or not instance.analysis_result:
        logger.warning(
            "Cannot serialize floorplan for SDB: Invalid instance or missing analysis_result."
        )
        return None

    # Build the analysis result payload
    analysis_result_payload = {
        "message": instance.analysis_result.message,
        "user_id": instance.analysis_result.user_id,
        "property_id": instance.analysis_result.property_id,
        # Include created_at/updated_at if needed by the SDB serializer, otherwise omit
        # "created_at": instance.analysis_result.created_at.isoformat() if instance.analysis_result.created_at else None,
        # "updated_at": instance.analysis_result.updated_at.isoformat() if instance.analysis_result.updated_at else None,
    }

    # Base payload for the FloorPlan itself
    payload = {
        "analysis_result": analysis_result_payload,
        "floorplan_id": instance.floorplan_id,
        "original_url": instance.original_url,
        "update_count": instance.update_count,
        # Initialize nested structures with 'sdb_' prefix expected by the receiver
        "sdb_all_floors_data": None,
        "sdb_plan_floors": [],
    }

    # Build the AllFloorsData payload if available.
    if hasattr(instance, "all_floors_data") and instance.all_floors_data:
        all_floors = instance.all_floors_data
        all_floors_payload = {
            "json_file_url": all_floors.json_file_url,
            "csv_url": all_floors.csv_url,
            "total_area_csv_url": all_floors.total_area_csv_url,
            "image_labelme_side_by_side_url": all_floors.image_labelme_side_by_side_url,
            "notes": all_floors.notes,
            # Initialize lists for nested structures with 'sdb_' prefix
            "sdb_csv_floors": [],
            "all_floors_csv_data": [],  # Match SDB serializer field name
            "total_areas_csv_data": [],  # Match SDB serializer field name
        }

        # Process Structured CSV floors (CsvFloor, CsvRoom, etc.)
        csv_floors_list = []
        for csv_floor in all_floors.csv_floors.all().prefetch_related(
            "rooms", "rooms__pixel_data", "rooms__dimensions", "rooms__scaling_factors"
        ):  # Prefetch for efficiency
            csv_floor_payload = {
                "floor_name": csv_floor.floor_name,
                "calculated_total_area_metric": csv_floor.calculated_total_area_metric,
                "calculated_total_area_imperial": csv_floor.calculated_total_area_imperial,
                "sdb_rooms": [],  # Use 'sdb_' prefix
            }
            rooms_list = []
            for room in csv_floor.rooms.all():
                room_payload = {
                    "room_name": room.room_name,
                    "is_segment": room.is_segment,
                    "room_id": room.room_id,
                    "no_of_doors": room.no_of_doors,
                    "no_of_windows": room.no_of_windows,
                    "no_of_room_points": room.no_of_room_points,
                    # Initialize nested detail structures
                    "sdb_pixel_data": None,
                    "sdb_dimensions": None,
                    "sdb_scaling_factors": None,
                }
                # Include pixel data if available
                if hasattr(room, "pixel_data") and room.pixel_data:
                    pd = room.pixel_data
                    room_payload["sdb_pixel_data"] = {  # Use 'sdb_' prefix
                        "min_x_pixels": pd.min_x_pixels,
                        "min_y_pixels": pd.min_y_pixels,
                        "max_x_pixels": pd.max_x_pixels,
                        "max_y_pixels": pd.max_y_pixels,
                        "max_area_pixels": pd.max_area_pixels,
                        "actual_area_pixels": pd.actual_area_pixels,
                        "pixel_ratio": pd.pixel_ratio,
                    }
                # Include dimensions if available
                if hasattr(room, "dimensions") and room.dimensions:
                    dims = room.dimensions
                    room_payload["sdb_dimensions"] = {  # Use 'sdb_' prefix
                        "dimensions_imperial": dims.dimensions_imperial,
                        "dimensions_metric": dims.dimensions_metric,
                        "max_area_metric": dims.max_area_metric,
                        "max_area_imperial": dims.max_area_imperial,
                        "calculated_sq_area_metric": dims.calculated_sq_area_metric,
                        "calculated_area_imperial": dims.calculated_area_imperial,
                    }
                # Include scaling factors if available
                if hasattr(room, "scaling_factors") and room.scaling_factors:
                    sf = room.scaling_factors
                    room_payload["sdb_scaling_factors"] = {  # Use 'sdb_' prefix
                        "scale_metric": sf.scale_metric,
                        "scale_imperial": sf.scale_imperial,
                    }
                rooms_list.append(room_payload)
            csv_floor_payload["sdb_rooms"] = rooms_list  # Use 'sdb_' prefix
            csv_floors_list.append(csv_floor_payload)
        all_floors_payload["sdb_csv_floors"] = csv_floors_list  # Use 'sdb_' prefix

        # Process Raw Row Data (AllFloorsCsvData) - Match SDB Serializer field name
        raw_rows_list = []
        # Efficiently serialize using values() - select only fields needed by SDB serializer
        raw_row_queryset = all_floors.all_floors_csv_data.values(
            "floor_name",
            "room_name",
            "is_segment",
            "dimensions_imperial",
            "dimensions_metric",
            "room_id",
            "no_of_door",
            "no_of_window",
            "no_of_room_points",
            "min_x_pixels",
            "min_y_pixels",
            "max_x_pixels",
            "max_y_pixels",
            "max_area_metric",
            "max_area_imperial",
            "max_area_pixels",
            "actual_area_pixels",
            "pixel_ratio",
            "scale_metric",
            "scale_imperial",
            "calculated_sq_area_metric",
            "calculated_floor_total_sq_area_metric",
            "calculated_area_imperial",
            "calculated_floor_total_sq_area_imperial",
        ).order_by(
            "id"
        )  # Order for consistency

        raw_rows_list = list(raw_row_queryset)  # Convert queryset to list of dicts
        all_floors_payload["all_floors_csv_data"] = raw_rows_list
        logger.debug("Serialized %d raw CSV rows for SDB.", len(raw_rows_list))

        # Process Total Area Data (TotalAreasCsvData) - Match SDB Serializer field name
        total_area_list = []
        total_area_queryset = all_floors.total_areas_csv_data.values(
            "area_name",
            "square_meters",
            "square_feet",
            "total_floors",
            "total_named_rooms",
            "total_segments",
            "total_points",
            "total_objects",
            "total_door_objects",
            "total_window_objects",
            "total_stair_objects",
            "list_of_objects",
            "total_actual_pixels",
            "metric_scale",
            "imperial_scale",
            "input_image_tokens",
            "input_text_tokens",
            "output_text_tokens",
        ).order_by(
            "id"
        )  # Order for consistency

        total_area_list = list(total_area_queryset)  # Convert queryset to list of dicts
        all_floors_payload["total_areas_csv_data"] = total_area_list
        logger.debug(
            "Serialized %d total area data rows for SDB.", len(total_area_list)
        )

        payload["sdb_all_floors_data"] = all_floors_payload  # Use 'sdb_' prefix
    else:
        logger.info(
            "No AllFloorsData found for FloorPlan ID %s, skipping related sdb data.",
            instance.floorplan_id,
        )

    # Process PlanFloor data.
    logger.debug("Serializing PlanFloor data for SDB...")
    sdb_plan_floors = []
    for pf in instance.plan_floors.all():
        pf_payload = {
            "floor": pf.floor,
            "label_me_url": pf.label_me_url,
            "json_file_url": pf.json_file_url,
            "image_url": pf.image_url,
            "labelme_image_url": pf.labelme_image_url,
            "csv_url": pf.csv_url,
            "image_side_by_side_url": pf.image_side_by_side_url,
        }
        sdb_plan_floors.append(pf_payload)
    payload["sdb_plan_floors"] = sdb_plan_floors  # Use 'sdb_' prefix
    logger.debug("Serialized %d PlanFloor entries for SDB.", len(sdb_plan_floors))

    return payload


# --- Main Backup Function (calls the serializer and sends) ---
def backup_floorplan(instance):
    """Serializes floorplan data for SDB and sends it to the backup service."""
    backup_url = None  # Define outside try block
    try:
        payload = serialize_floorplan_for_sdb(instance)
        if payload is None:
            # Serialization failed, error already logged in helper
            return

        # Send the payload to the SDB endpoint.
        # Make sure the path matches sdb/urls.py -> /api/sdb/floorplan/
        base_url = settings.BACKUP_SERVICE_URL.rstrip("/")
        backup_url = f"{base_url}/api/sdb/floorplan/"  # Adjusted path

        logger.info(
            "Sending SDB payload for FloorPlan ID %s to %s",
            instance.floorplan_id,
            backup_url,
        )
        response = requests.post(
            backup_url, json=payload, timeout=30
        )  # Increased timeout
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        logger.info(
            "SDB sync successful for FloorPlan ID %s. Response status: %s",
            instance.floorplan_id,
            response.status_code,
        )
    except requests.exceptions.Timeout:
        logger.error(
            "Timeout occurred while sending SDB sync for FloorPlan ID %s to %s",
            instance.floorplan_id,
            backup_url or "N/A",
        )
        # Consider if retry is needed here within the Celery task context
        # raise Exception(f"Timeout syncing floorplan {instance.floorplan_id} to SDB") from None
    except requests.HTTPError as http_err:
        error_details = "No response body"
        try:
            error_details = http_err.response.text
        except Exception:
            logger.warning("Could not decode error response body for SDB sync failure.")
        logger.error(
            "HTTP Error syncing SDB for FloorPlan ID %s: %s - Status Code: %s - Details: %s",
            instance.floorplan_id,
            str(http_err),
            http_err.response.status_code if http_err.response else "N/A",
            error_details,
        )
        # raise Exception(f"HTTP error syncing floorplan {instance.floorplan_id} to SDB: {str(http_err)}") from http_err
    except requests.RequestException as req_err:
        logger.error(
            "Request Exception during SDB sync for FloorPlan ID %s: %s",
            instance.floorplan_id,
            str(req_err),
        )
        # raise Exception(f"Request error syncing floorplan {instance.floorplan_id} to SDB: {str(req_err)}") from req_err
    except Exception as e:
        logger.exception(
            "Unexpected error during SDB sync process for FloorPlan ID %s: %s",
            instance.floorplan_id,
            str(e),
        )
        # raise Exception(f"Failed to complete SDB sync for floorplan {instance.floorplan_id}") from e
