import requests
import os

## CUSTOM FUNCTIONS ##
def get_data_from_url(url):
    try:
        headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0'
        }
        response = requests.get(url, headers=headers)
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
print("Grabbing USDA Food Safety Recall RSS XML")
usda_rss_res = get_data_from_url("https://www.fsis.usda.gov/fsis-content/rss/recalls.xml")
usda_rss_txt = usda_rss_res.text # Parsing as text

# Getting script folder
script_dir = os.path.dirname(__file__)
target_folder_rel_path = "../raw_data"
output_file_path = os.path.join(script_dir, target_folder_rel_path, "usda_food_safety_recalls.xml")

# Writing out raw RSS XML to the `raw_data` folder
with open(output_file_path, "w") as f:
    f.write(usda_rss_txt)

print("Writing out USDA Food Safety Recall RSS XML to ./raw_data/usda_food_safety_recall.xml")