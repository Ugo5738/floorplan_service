import requests
from django.conf import settings
from django.forms.models import model_to_dict


def backup_floorplan(instance):
    # Start with the FloorPlan instance data.
    payload = model_to_dict(instance)

    # Add data from the analysis result.
    if instance.analysis_result:
        payload["analysis_result"] = model_to_dict(instance.analysis_result)

    # Add AllFloorsData and its CSV-related data.
    if hasattr(instance, "all_floors_data"):
        all_floors_data = model_to_dict(instance.all_floors_data)

        # Serialize CSV floors (each CSV floor and its rooms)
        csv_floors_list = []
        for csv_floor in instance.all_floors_data.csv_floors.all():
            csv_floor_dict = model_to_dict(csv_floor)
            rooms_list = []
            for room in csv_floor.rooms.all():
                room_dict = model_to_dict(room)
                # Include related pixel data if available
                if hasattr(room, "pixel_data"):
                    room_dict["pixel_data"] = model_to_dict(room.pixel_data)
                # Include dimension data if available
                if hasattr(room, "dimensions"):
                    room_dict["dimensions"] = model_to_dict(room.dimensions)
                # Include scaling factors if available
                if hasattr(room, "scaling_factors"):
                    room_dict["scaling_factors"] = model_to_dict(room.scaling_factors)
                rooms_list.append(room_dict)
            csv_floor_dict["rooms"] = rooms_list
            csv_floors_list.append(csv_floor_dict)
        all_floors_data["csv_floors"] = csv_floors_list
        payload["all_floors_data"] = all_floors_data

    # Add plan floors data
    payload["plan_floors"] = [model_to_dict(pf) for pf in instance.plan_floors.all()]

    backup_url = f"{settings.BACKUP_SERVICE_URL}/api/backup/floorplan/"
    response = requests.post(backup_url, json=payload, timeout=5)
    response.raise_for_status()
