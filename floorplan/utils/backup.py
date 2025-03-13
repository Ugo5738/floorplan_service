import requests
from django.conf import settings
from django.forms.models import model_to_dict


def backup_floorplan(instance):
    payload = {}

    # Serialize the analysis result
    if instance.analysis_result:
        payload["backup_floorplananalysisresult"] = model_to_dict(
            instance.analysis_result
        )

    # Serialize the main FloorPlan data
    payload["backup_floorplan"] = model_to_dict(instance)

    # Serialize AllFloorsData if available
    if hasattr(instance, "all_floors_data"):
        all_floors_data = model_to_dict(instance.all_floors_data)
        # Serialize CSV floors and nested rooms data
        csv_floors_list = []
        for csv_floor in instance.all_floors_data.csv_floors.all():
            csv_floor_dict = model_to_dict(csv_floor)
            rooms_list = []
            for room in csv_floor.rooms.all():
                room_dict = model_to_dict(room)
                if hasattr(room, "pixel_data"):
                    room_dict["backup_csvroompixeldata"] = model_to_dict(
                        room.pixel_data
                    )
                if hasattr(room, "dimensions"):
                    room_dict["backup_csvroomdimensions"] = model_to_dict(
                        room.dimensions
                    )
                if hasattr(room, "scaling_factors"):
                    room_dict["backup_csvroomscalingfactors"] = model_to_dict(
                        room.scaling_factors
                    )
                rooms_list.append(room_dict)
            csv_floor_dict["backup_rooms"] = rooms_list
            csv_floors_list.append(csv_floor_dict)
        all_floors_data["backup_csv_floors"] = csv_floors_list
        payload["backup_all_floors_data"] = all_floors_data

    # Serialize PlanFloor data
    payload["backup_plan_floors"] = [
        model_to_dict(pf) for pf in instance.plan_floors.all()
    ]

    # Send the structured payload to your backup service
    backup_url = f"{settings.BACKUP_SERVICE_URL}/api/backup/floorplan/"
    response = requests.post(backup_url, json=payload, timeout=5)
    response.raise_for_status()
