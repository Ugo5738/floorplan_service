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
    payload.update(floorplan_data)

    # If AllFloorsData exists, include it (with nested CSV floors/rooms).
    if hasattr(instance, "all_floors_data"):
        all_floors_data = model_to_dict(instance.all_floors_data)
        # Process CSV floors (nested under the key 'backup_csv_floors')
        csv_floors_list = []
        for csv_floor in instance.all_floors_data.csv_floors.all():
            csv_floor_dict = model_to_dict(csv_floor)
            # Process nested CSV rooms for this floor.
            rooms_list = []
            for room in csv_floor.rooms.all():
                room_dict = model_to_dict(room)
                # Add nested relations if they exist.
                if hasattr(room, "pixel_data"):
                    room_dict["backup_pixel_data"] = model_to_dict(room.pixel_data)
                if hasattr(room, "dimensions"):
                    room_dict["backup_dimensions"] = model_to_dict(room.dimensions)
                if hasattr(room, "scaling_factors"):
                    room_dict["backup_scaling_factors"] = model_to_dict(
                        room.scaling_factors
                    )
                rooms_list.append(room_dict)
            csv_floor_dict["backup_rooms"] = rooms_list
            csv_floors_list.append(csv_floor_dict)
        all_floors_data["backup_csv_floors"] = csv_floors_list
        payload["backup_all_floors_data"] = all_floors_data

    # Process PlanFloor data (store as backup_plan_floors)
    backup_plan_floors = [model_to_dict(pf) for pf in instance.plan_floors.all()]
    payload["backup_plan_floors"] = backup_plan_floors

    # Send the payload to the backup service endpoint.
    backup_url = f"{settings.BACKUP_SERVICE_URL}/api/backup/floorplan/"
    response = requests.post(backup_url, json=payload, timeout=5)
    response.raise_for_status()
