import requests
from django.conf import settings
from django.forms.models import model_to_dict


def backup_floorplan(instance):
    payload = {}

    # Map the analysis result to the key expected by the backup serializer.
    if instance.analysis_result:
        payload["analysis_result"] = model_to_dict(instance.analysis_result)

    # Include main FloorPlan fields (e.g. floorplan_id, original_url, etc.)
    floorplan_data = model_to_dict(instance)
    floorplan_data.pop(
        "analysis_result", None
    )  # Remove the FK ID that model_to_dict returns.
    floorplan_data.pop("id", None)  # Remove the FloorPlan's primary key.
    payload.update(floorplan_data)

    # If AllFloorsData exists, include it (with nested CSV floors/rooms).
    if hasattr(instance, "all_floors_data"):
        all_floors_data = model_to_dict(instance.all_floors_data)
        all_floors_data.pop("id", None)  # Remove the primary key.

        # Process CSV floors (nested under the key 'backup_csv_floors')
        csv_floors_list = []
        for csv_floor in instance.all_floors_data.csv_floors.all():
            csv_floor_dict = model_to_dict(csv_floor)
            csv_floor_dict.pop("id", None)

            # Process nested CSV rooms for this floor.
            rooms_list = []
            for room in csv_floor.rooms.all():
                room_dict = model_to_dict(room)
                room_dict.pop("id", None)

                # Add nested relations if they exist.
                if hasattr(room, "pixel_data"):
                    pd = model_to_dict(room.pixel_data)
                    pd.pop("id", None)
                    room_dict["backup_pixel_data"] = pd
                if hasattr(room, "dimensions"):
                    dims = model_to_dict(room.dimensions)
                    dims.pop("id", None)
                    room_dict["backup_dimensions"] = dims
                if hasattr(room, "scaling_factors"):
                    sf = model_to_dict(room.scaling_factors)
                    sf.pop("id", None)
                    room_dict["backup_scaling_factors"] = sf
                rooms_list.append(room_dict)
            csv_floor_dict["backup_rooms"] = rooms_list
            csv_floors_list.append(csv_floor_dict)
        all_floors_data["backup_csv_floors"] = csv_floors_list
        payload["backup_all_floors_data"] = all_floors_data

    # Process PlanFloor data (store as backup_plan_floors)
    backup_plan_floors = []
    for pf in instance.plan_floors.all():
        pf_data = model_to_dict(pf)
        pf_data.pop("id", None)
        backup_plan_floors.append(pf_data)
    payload["backup_plan_floors"] = backup_plan_floors

    # Send the payload to the backup service endpoint.
    backup_url = f"{settings.BACKUP_SERVICE_URL}/api/backup/floorplan/"
    response = requests.post(backup_url, json=payload, timeout=5)
    response.raise_for_status()
