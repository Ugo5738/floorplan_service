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


# SAMPLES
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


# {
#     "user_id": "supersami54567",
#     "property_id": "rightmove2345",
#     "webhook_url": "https://webhook.site/045c3250-4281-473f-afab-60efed651a28",
#     "floorplans": {
#         "fp1": {
#             "url": "https://i.postimg.cc/B6gf1wmL/1-FP-Data-1.png",
#             "notes": "this is first floor.",
#         },
#         "fp2": {
#             "url": "https://i.postimg.cc/d1vK3Kjc/2-FP-Data-2.png",
#             "notes": "this is second floor.",
#         },
#     },
# }

# {
#     "task": "creation",
#     "message": "Floor plans processed successfully",
#     "user_id": "supersami54567",
#     "property_id": "rightmove2345",
#     "output_data": [
#         {
#             "floorplan_id": "fp1",
#             "original_url": "https://i.postimg.cc/B6gf1wmL/1-FP-Data-1.png",
#             "all_floors": {
#                 "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/all_floors_json.json",
#                 "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/all_floors.csv",
#                 "total_area_csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/total_area.csv",
#                 "image_labelme_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/side_by_side_labelme.png",
#                 "notes": "this is first floor.",
#             },
#             "floors": [
#                 {
#                     "floor": "first_floor",
#                     "label_me_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/first_floor",
#                     "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/first_floor/first_floor.json",
#                     "image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/first_floor/first_floor.png",
#                     "labelme_image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/first_floor/first_floor_labelmes.png",
#                     "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/first_floor/first_floor.csv",
#                     "image_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/first_floor/first_floor_side_by_side_labelme.png",
#                 },
#                 {
#                     "floor": "ground_floor",
#                     "label_me_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/ground_floor",
#                     "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/ground_floor/ground_floor.json",
#                     "image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/ground_floor/ground_floor.png",
#                     "labelme_image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/ground_floor/ground_floor_labelmes.png",
#                     "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/ground_floor/ground_floor.csv",
#                     "image_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp1/ground_floor/ground_floor_side_by_side_labelme.png",
#                 },
#             ],
#         },
#         {
#             "floorplan_id": "fp2",
#             "original_url": "https://i.postimg.cc/d1vK3Kjc/2-FP-Data-2.png",
#             "all_floors": {
#                 "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/all_floors_json.json",
#                 "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/all_floors.csv",
#                 "total_area_csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/total_area.csv",
#                 "image_labelme_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/side_by_side_labelme.png",
#                 "notes": "this is first floor.",
#             },
#             "floors": [
#                 {
#                     "floor": "1st_floor",
#                     "label_me_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/1st_floor",
#                     "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/1st_floor/1st_floor.json",
#                     "image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/1st_floor/1st_floor.png",
#                     "labelme_image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/1st_floor/1st_floor_labelmes.png",
#                     "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/1st_floor/1st_floor.csv",
#                     "image_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/1st_floor/1st_floor_side_by_side_labelme.png",
#                 },
#                 {
#                     "floor": "ground_floor",
#                     "label_me_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/ground_floor",
#                     "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/ground_floor/ground_floor.json",
#                     "image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/ground_floor/ground_floor.png",
#                     "labelme_image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/ground_floor/ground_floor_labelmes.png",
#                     "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/ground_floor/ground_floor.csv",
#                     "image_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_123_property_1/floorid_fp2/ground_floor/ground_floor_side_by_side_labelme.png",
#                 },
#             ],
#         },
#     ],
# }


[
    {
        "floorplan_id": "fp1",
        "original_url": "https://media.rightmove.co.uk/85k/84073/157593251/84073_1312423_FLP_00_0001.png",
        "all_floors": {  #
            "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/all_floors_json.json",
            "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/all_floors.csv",
            "total_area_csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/total_area.csv",
            "image_labelme_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/side_by_side_labelme.png",
            "notes": "",
        },
        "floors": [
            {
                "floor": "unknown",
                "label_me_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/unknown",
                "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/unknown/unknown.json",
                "image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/unknown/unknown.png",
                "labelme_image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/unknown/unknown_labelmes.png",
                "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/unknown/unknown.csv",
                "image_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_sami1234_property_samiprop1234/floorid_fp1/unknown/unknown_side_by_side_labelme.png",
            }
        ],
    }
]
