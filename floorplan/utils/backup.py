import requests
from django.conf import settings
from django.forms.models import model_to_dict


def backup_floorplan(instance):
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
    if hasattr(instance, "all_floors_data"):
        all_floors = instance.all_floors_data
        all_floors_payload = {
            "json_file_url": all_floors.json_file_url,
            "csv_url": all_floors.csv_url,
            "total_area_csv_url": all_floors.total_area_csv_url,
            "image_labelme_side_by_side_url": all_floors.image_labelme_side_by_side_url,
            "notes": all_floors.notes,
        }

        # Process CSV floors
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
                        # The backup model also has fields for total floor area;
                        # if you don't have values, send None:
                        "calculated_floor_total_sq_area_metric": None,
                        "calculated_area_imperial": dims.calculated_area_imperial,
                        "calculated_floor_total_sq_area_imperial": None,
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

    # Process PlanFloor data.
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

    # Send the payload to the backup endpoint.
    backup_url = f"{settings.BACKUP_SERVICE_URL}/api/backup/floorplan/"
    try:
        response = requests.post(backup_url, json=payload, timeout=5)
        # If there is a 400 or any HTTP error, log the response details.
        response.raise_for_status()
    except requests.HTTPError as e:
        # Log response content to help pinpoint which field is causing validation to fail.
        error_details = response.content.decode()
        print(f"Backup service error details: {error_details}")
        raise Exception(f"Error backing up floorplan {instance.floorplan_id}: {str(e)}")
