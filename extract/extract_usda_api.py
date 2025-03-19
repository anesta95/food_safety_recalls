import requests
import os
import json

## CUSTOM FUNCTIONS ##
def get_data_from_url(url):
    try:
        headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0'
        }
        response = requests.get(url, headers=headers, allow_redirects=False, timeout=30)
        response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
        return response  # Return the response data
    except requests.exceptions.HTTPError as err:
        print(f"HTTP Error {err.response.status_code}: {url}")
        return None  # Return None to indicate an error
    except requests.exceptions.ConnectionError as err:
        print(f"Connection Error: {err}")
        return None  # Return None to indicate an error
    except requests.exceptions.Timeout as err:
        print(f"Timeout Error: {err}")
        return None  # Return None to indicate an error
    except requests.exceptions.RequestException as err:
        print(f"Request Error: {err}")
        return None  # Return None to indicate an error

# Getting latest USDA FSIS food safety alert webpages from their RSS feed
# The `field_year_id` argument will have to be changed every year. 
# Values can be found in documentation here: https://www.fsis.usda.gov/sites/default/files/media_file/documents/Recall-API-documentation.pdf
# landing page here: https://www.fsis.usda.gov/science-data/developer-resources/recall-api
print("Grabbing USDA Food Safety Recall API JSON")
usda_api_res = get_data_from_url("https://www.fsis.usda.gov/fsis/api/recall/v/1")
usda_api_json = usda_api_res.json() # Parsing as JSON

# Getting script folder
script_dir = os.path.dirname(__file__)
target_folder_rel_path = "../raw_data"
output_file_path = os.path.join(script_dir, target_folder_rel_path, "usda_food_safety_recalls.json")

# Writing out dict as JSON
with open(output_file_path, 'w') as f:
    json.dump(usda_api_json, f, indent=4, separators=(",", ": "))

print("Writing out USDA Food Safety Recall API JSON to ./raw_data/usda_food_safety_recalls.json")
