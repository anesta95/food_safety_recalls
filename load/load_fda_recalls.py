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
fda_staged_recalls = load_json_file("fda_food_safety_recalls_staged.json", "../transformed_staged_data")

overall_latest_dttm = get_latest_json_dttm(overall_food_recalls, agency="FDA")
fda_staged_latest_dttm = get_latest_json_dttm(fda_staged_recalls)

if fda_staged_latest_dttm > overall_latest_dttm:
    print("New FDA data to be added:\n")
    add_latest_json(fda_staged_recalls, overall_food_recalls, overall_latest_dttm, "food_safety_recalls.json", "../clean_data")
else:
    print("No new FDA data to be added.")

## TODO: Do I want in-place updates to update in-place in the final JSON or show up as new nodes?