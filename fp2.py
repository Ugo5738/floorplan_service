import json

import requests

# API endpoint URL
url = "http://165.232.101.36/fpextractor"

# Payload to send
payload = {
    "user_id": "supersami54567",
    "property_id": "rightmove2345",
    "floorplans": {
        "fp1": {
            "url": "https://media.rightmove.co.uk/267k/266045/156762020/266045_S1179014_FLP_00_0001.jpeg",
            "notes": "",
        }
    },
}

# Set the headers to indicate that we are sending JSON
headers = {"Content-Type": "application/json"}

# Send the POST request
response = requests.post(url, json=payload, headers=headers)

# Print the response from the API
print(json.dumps(response.json(), indent=4))


# {
#     "message": "Floor plans processed successfully",
#     "user_id": "supersami54567",
#     "property_id": "rightmove2345",
#     "output_data": [
#         {
#             "floorplan_id": "fp1",
#             "original_url": "https://media.rightmove.co.uk/267k/266045/156762020/266045_S1179014_FLP_00_0001.jpeg",
#             "all_floors": {
#                 "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/all_floors_json.json",
#                 "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/all_floors.csv",
#                 "total_area_csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/total_area.csv",
#                 "image_labelme_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/side_by_side_labelme.png",
#                 "notes": "",
#             },
#             "floors": [
#                 {
#                     "floor": "first_floor",
#                     "label_me_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor",
#                     "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor.json",
#                     "image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor.png",
#                     "labelme_image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor_labelmes.png",
#                     "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor.csv",
#                     "image_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/first_floor/first_floor_side_by_side_labelme.png",
#                 },
#                 {
#                     "floor": "ground_floor",
#                     "label_me_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/ground_floor",
#                     "json_file_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/ground_floor/ground_floor.json",
#                     "image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/ground_floor/ground_floor.png",
#                     "labelme_image_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/ground_floor/ground_floor_labelmes.png",
#                     "csv_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/ground_floor/ground_floor.csv",
#                     "image_side_by_side_url": "https://floorsbucket.s3.eu-north-1.amazonaws.com/processed_images_folder/user_supersami54567_property_rightmove2345/floorid_fp1/ground_floor/ground_floor_side_by_side_labelme.png",
#                 },
#             ],
#         }
#     ],
# }
