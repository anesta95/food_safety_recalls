import os
import json
from zoneinfo import ZoneInfo
from datetime import datetime

## CUSTOM CLASSES ##
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)

## CUSTOM FUNCTIONS ##
def load_json_file(file_name, rel_file_folder_path):
    script_dir = os.path.dirname(__file__)
    data_file_path = os.path.join(script_dir, rel_file_folder_path, file_name)

    with open(data_file_path, "r") as f:
        json_data = json.load(f)
    
    return json_data

def get_latest_json_dttm(json_list, agency="all"):
    if agency == "all":
        latest_dttm = datetime.fromtimestamp(0, tz=ZoneInfo("UTC"))
        for recall in json_list:
            recall_ddtm = datetime.strptime(recall["notification_dttm"], "%Y-%m-%dT%H:%M:%S%z")
            if recall_ddtm > latest_dttm:
                latest_dttm = recall_ddtm
    else:
        latest_dttm = datetime.fromtimestamp(0, tz=ZoneInfo("UTC"))
        for recall in json_list:
            recall_ddtm = datetime.strptime(recall["notification_dttm"], "%Y-%m-%dT%H:%M:%S%z")
            if (recall["agency"] == agency and recall_ddtm > latest_dttm):
                latest_dttm = recall_ddtm
    return latest_dttm

def add_latest_json(staged_json_list, overall_json_list, latest_dttm, overall_file_name, overall_rel_file_folder_path):
    script_dir = os.path.dirname(__file__)
    data_file_path = os.path.join(script_dir, overall_rel_file_folder_path, overall_file_name)

    for recall in staged_json_list:
        recall_ddtm = datetime.strptime(recall["notification_dttm"], "%Y-%m-%dT%H:%M:%S%z")
        if recall_ddtm > latest_dttm:
            print(f"Adding data from recall {recall["title"]} at {recall["recall_url"]}.\n")
            overall_json_list.insert(0, recall)
    
    with open(data_file_path, 'w') as f:
        json.dump(overall_json_list, f, indent=4, separators=(",", ": "), cls=DateTimeEncoder)

## ACTUAL SCRIPT ##
overall_food_recalls = load_json_file("food_safety_recalls.json", "../clean_data")
usda_staged_recalls = load_json_file("usda_food_safety_recalls_staged.json", "../transformed_staged_data")

overall_latest_dttm = get_latest_json_dttm(overall_food_recalls, agency="USDA")
usda_staged_latest_dttm = get_latest_json_dttm(usda_staged_recalls)

if usda_staged_latest_dttm > overall_latest_dttm:
    print("New USDA data to be added:\n")
    add_latest_json(usda_staged_recalls, overall_food_recalls, overall_latest_dttm, "food_safety_recalls.json", "../clean_data")

# TODO: Load latest USDA data date from `clean_data/food_safety_recalls.json`
# TODO: Use the latest USDA data date in a loop through the data in 
# `transformed_staged_data/usda_food_safety_recalls_staged.json`
# and add any nodes released after the date to the `clean_data/food_safety_recalls.json`
# TODO: Write out final `clean_data/food_safety_recalls.json` data.