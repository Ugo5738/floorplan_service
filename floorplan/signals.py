# from django.db.models.signals import post_save
# from django.dispatch import receiver

# from floorplan.models import FloorPlan
# from floorplan.utils.backup import backup_floorplan


# @receiver(post_save, sender=FloorPlan)
# def backup_floorplan_handler(sender, instance, created, **kwargs):
#     # Optionally, you can check for 'created' or even filter updates if needed.
#     try:
#         backup_floorplan(instance)
#     except Exception as e:
#         # Log error; you may want to implement retry logic or asynchronous backup here.
#         print("Error backing up property:", e)


# {
#     "task": "update",
#     "user_id": "supersami54567",
#     "property_id": "rightmove2345",
#     "output_data": {
#         "floorplan_id": "fp1",
#         "floors": {
#             "floor": "first_floor",  # floor that is to be updated
#             "label_me_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor",
#             "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor.json",
#             "image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor.png",
#             "labelme_image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor_labelmes.png",
#             "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor.csv",
#             "image_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor_side_by_side_labelme.png",
#         },
#     },
# }
