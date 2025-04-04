import requests
from django.conf import settings
from django.forms.models import model_to_dict

from floorplan_service.config.logging_config import configure_logger

logger = configure_logger(__name__)


def backup_floorplan(instance):
    try:
        logger.info(
            "Starting backup process for FloorPlan ID: %s", instance.floorplan_id
        )
        # Build the analysis result payload (exclude auto fields)
        analysis_result_payload = {
            "message": instance.analysis_result.message,
            "user_id": instance.analysis_result.user_id,
            "property_id": instance.analysis_result.property_id,
        }

        # Build the main floorplan payload – only required fields.
        payload = {
            "analysis_result": analysis_result_payload,
            "floorplan_id": instance.floorplan_id,
            "original_url": instance.original_url,
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
                # Initialize lists for nested structures
                "backup_csv_floors": [],
                "backup_all_floors_raw_rows": [],  # <-- Initialize raw rows list
                "backup_total_area_data": [],  # <-- Initialize total area list (if backing up)
            }

            # Process Structured CSV floors (CsvFloor, CsvRoom, etc.)
            csv_floors_list = []
            for csv_floor in all_floors.csv_floors.all():
                csv_floor_payload = {
                    "floor_name": csv_floor.floor_name,
                    "calculated_total_area_metric": csv_floor.calculated_total_area_metric,
                    "calculated_total_area_imperial": csv_floor.calculated_total_area_imperial,
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
                    }
                    # Include pixel data if available
                    if hasattr(room, "pixel_data"):
                        pd = room.pixel_data
                        room_payload["backup_pixel_data"] = {
                            "min_x_pixels": pd.min_x_pixels,
                            "min_y_pixels": pd.min_y_pixels,
                            "max_x_pixels": pd.max_x_pixels,
                            "max_y_pixels": pd.max_y_pixels,
                            "max_area_pixels": pd.max_area_pixels,
                            "actual_area_pixels": pd.actual_area_pixels,
                            "pixel_ratio": pd.pixel_ratio,
                        }
                    # Include dimensions if available
                    if hasattr(room, "dimensions"):
                        dims = room.dimensions
                        room_payload["backup_dimensions"] = {
                            "dimensions_imperial": dims.dimensions_imperial,
                            "dimensions_metric": dims.dimensions_metric,
                            "max_area_metric": dims.max_area_metric,
                            "max_area_imperial": dims.max_area_imperial,
                            "calculated_sq_area_metric": dims.calculated_sq_area_metric,
                            "calculated_area_imperial": dims.calculated_area_imperial,
                        }
                    # Include scaling factors if available
                    if hasattr(room, "scaling_factors"):
                        sf = room.scaling_factors
                        room_payload["backup_scaling_factors"] = {
                            "scale_metric": sf.scale_metric,
                            "scale_imperial": sf.scale_imperial,
                        }
                    rooms_list.append(room_payload)
                csv_floor_payload["backup_rooms"] = rooms_list
                csv_floors_list.append(csv_floor_payload)
            all_floors_payload["backup_csv_floors"] = csv_floors_list
            payload["backup_all_floors_data"] = all_floors_payload

            # --- Process Raw Row Data (AllFloorsCsvRawRow) ---
            raw_rows_list = []
            # Efficiently serialize using model_to_dict or values()
            raw_row_queryset = all_floors.all_floors_raw_rows.all().order_by(
                "id"
            )  # Order for consistency
            for raw_row in raw_row_queryset:
                # Exclude the foreign key object itself to avoid circular refs
                raw_row_dict = model_to_dict(raw_row, exclude=["all_floors_data"])
                # Could add the parent ID explicitly if needed
                # raw_row_dict['all_floors_data_id'] = raw_row.all_floors_data_id
                raw_rows_list.append(raw_row_dict)
            all_floors_payload["backup_all_floors_raw_rows"] = raw_rows_list
            logger.debug("Serialized %d raw CSV rows.", len(raw_rows_list))
            # --- END Raw Row Data ---

            # --- Process Total Area Data (TotalAreaData) --- Optional, include if needed
            logger.debug("Serializing total area data for backup...")
            total_area_list = []
            total_area_queryset = all_floors.total_area_data.all().order_by(
                "id"
            )  # Order for consistency
            for ta_data in total_area_queryset:
                # Exclude the foreign key object
                ta_data_dict = model_to_dict(ta_data, exclude=["all_floors_data"])
                total_area_list.append(ta_data_dict)
            all_floors_payload["backup_total_area_data"] = total_area_list
            logger.debug("Serialized %d total area data rows.", len(total_area_list))
            # --- END Total Area Data ---

            payload["backup_all_floors_data"] = all_floors_payload
        else:
            logger.info(
                "No AllFloorsData found for FloorPlan ID %s, skipping related backup data.",
                instance.floorplan_id,
            )

        # Process PlanFloor data.
        logger.debug("Serializing PlanFloor data...")
        backup_plan_floors = []
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
            backup_plan_floors.append(pf_payload)
        payload["backup_plan_floors"] = backup_plan_floors
        logger.debug("Serialized %d PlanFloor entries.", len(backup_plan_floors))

        # Send the payload to the backup endpoint.
        backup_url = f"{settings.BACKUP_SERVICE_URL}/api/backup/floorplan/"
        logger.info(
            "Sending backup payload for FloorPlan ID %s to %s",
            instance.floorplan_id,
            backup_url,
        )
        response = requests.post(backup_url, json=payload, timeout=5)
        # If there is a 400 or any HTTP error, log the response details.
        response.raise_for_status()
        logger.info(
            "Backup successful for FloorPlan ID %s. Response status: %s",
            instance.floorplan_id,
            response.status_code,
        )
    except requests.exceptions.Timeout:
        logger.error(
            "Timeout occurred while sending backup for FloorPlan ID %s to %s",
            instance.floorplan_id,
            backup_url,
        )
        # Re-raise or handle as needed - maybe retry?
        raise Exception(
            f"Timeout backing up floorplan {instance.floorplan_id}"
        ) from None
    except requests.HTTPError as http_err:
        # Log response content to help pinpoint validation errors on the backup service
        error_details = "No response body"
        try:
            error_details = (
                http_err.response.text
            )  # Use .text for JSON or other text formats
        except Exception:
            logger.warning("Could not decode error response body for backup failure.")

        logger.error(
            "HTTP Error backing up FloorPlan ID %s: %s - Status Code: %s - Details: %s",
            instance.floorplan_id,
            str(http_err),
            http_err.response.status_code,
            error_details,
        )
        raise Exception(
            f"HTTP error backing up floorplan {instance.floorplan_id}: {str(http_err)}"
        ) from http_err
    except requests.RequestException as req_err:
        logger.error(
            "Request Exception during backup for FloorPlan ID %s: %s",
            instance.floorplan_id,
            str(req_err),
        )
        raise Exception(
            f"Request error backing up floorplan {instance.floorplan_id}: {str(req_err)}"
        ) from req_err
    except Exception as e:
        # Catch any other unexpected errors during serialization or processing
        logger.exception(
            "Unexpected error during backup process for FloorPlan ID %s: %s",
            instance.floorplan_id,
            str(e),
        )
        raise Exception(
            f"Failed to complete backup for floorplan {instance.floorplan_id}"
        ) from e
