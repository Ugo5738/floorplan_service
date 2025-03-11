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
