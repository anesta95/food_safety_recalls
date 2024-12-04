import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import uuid
import xml.etree.ElementTree as ET

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

def empty_string_checker(raw_dict_val_str):
    replacement_val = None
    if raw_dict_val_str == "":
        return replacement_val
    else:
        return raw_dict_val_str

def change_timezones(dttm, tz_dest):
    NEW_TZ = ZoneInfo(tz_dest)
    dttm_new_tz = dttm.astimezone(NEW_TZ)
    return dttm_new_tz

def parse_dttm(dttm_str, format_string):
    dttm = datetime.strptime(dttm_str, format_string)
    return dttm

def find_state_postal_codes(state_list, present_states):
    if present_states == "":
        state_abbs = []
    else:
        matching_indices = [i for i, element in enumerate(state_list[1]) if element in present_states]
        state_abbs = [state_list[0][i] for i in matching_indices]
    return state_abbs

def find_usda_recall_url(title_str, xml_folder, xml_filename):
    script_dir = os.path.dirname(__file__)
    xml_data_folder_rel_path = xml_folder
    xml_data_file_path = os.path.join(script_dir, xml_data_folder_rel_path, xml_filename)

    tree = ET.parse(xml_data_file_path)
    root = tree.getroot()

    recall_url = None

    for item in root.iterfind(".//item"):
        recall_title = item.find("title").text.strip()
        xml_recall_url = item.find("guid").text.strip()
        if title_str == recall_title:
            recall_url = xml_recall_url
    
    if not recall_url:
        print(f"Could not find corresponding URL for recall {title_str}, leaving value empty")
        recall_url = None
    
    return recall_url


def transform_usda_node(dict, state_list, xml_folder, xml_filename):
    title = empty_string_checker(dict["field_title"])
    company_announce_dttm = None
    notification_dttm_str = dict["field_recall_date"]
    notification_dttm = change_timezones(parse_dttm(notification_dttm_str, "%Y-%m-%d"), "UTC")
    recall_reason = empty_string_checker(dict["field_recall_reason"])
    company_name = empty_string_checker(dict["field_establishment"])
    brand_name = None
    product_description = empty_string_checker(dict["field_product_items"])
    impacted_states = find_state_postal_codes(state_list, dict["field_states"])
    agency = "USDA"
    uid = str(uuid.uuid4())
    recall_url = find_usda_recall_url(title, xml_folder, xml_filename)
    notice_id_number = empty_string_checker(dict["field_recall_number"])
    recall_type = empty_string_checker(dict["field_recall_type"])
    risk_level = empty_string_checker(dict["field_risk_level"])
    recall_classification = empty_string_checker(dict["field_recall_classification"])

    usda_dict = {
        "title": title,
        "company_announce_dttm": company_announce_dttm,
        "notification_dttm": notification_dttm,
        "recall_reason": recall_reason,
        "company_name": company_name,
        "brand_name": brand_name,
        "product_description": product_description,
        "impacted_states": impacted_states,
        "agency": agency,
        "uid": uid,
        "recall_url": recall_url,
        "notice_id_number": notice_id_number,
        "recall_type": recall_type,
        "risk_level": risk_level,
        "recall_classification": recall_classification
    }

    return usda_dict

## OBJECTS ##
states = [
    [
        "AL",
        "AK",
        "AS",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FM",
        "FL",
        "GA",
        "GU",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MH",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "US",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "MP",
        "OH",
        "OK",
        "OR",
        "PW",
        "PA",
        "PR",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VI",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY"
    ],
    [
        "Alabama",
        "Alaska",
        "American Samoa",
        "Arizona",
        "Arkansas",	
        "California",
        "Colorado",
        "Connecticut",
        "Delaware",
        "District of Columbia",
        "Federated States of Micronesia",
        "Florida",
        "Georgia",
        "Guam",
        "Hawaii",
        "Idaho",
        "Illinois",
        "Indiana",
        "Iowa",
        "Kansas",
        "Kentucky",
        "Louisiana",
        "Maine",
        "Marshall Islands",
        "Maryland",
        "Massachusetts",
        "Michigan",
        "Minnesota",
        "Mississippi",
        "Missouri",
        "Montana",
        "nationwide",
        "Nebraska",
        "Nevada",
        "New Hampshire",
        "New Jersey",
        "New Mexico",
        "New York",
        "North Carolina",
        "North Dakota",
        "Northern Mariana Islands",
        "Ohio",
        "Oklahoma",
        "Oregon",
        "Palau",
        "Pennsylvania",
        "Puerto Rico",
        "Rhode Island",
        "South Carolina",
        "South Dakota",
        "Tennessee",
        "Texas",
        "Utah",
        "Vermont",
        "Virgin Islands",
        "Virginia",
        "Washington",
        "West Virginia",
        "Wisconsin",
        "Wyoming"
    ]
]

## ACTUAL SCRIPT ##

raw_usda_json = load_json_file("usda_food_safety_recalls.json", "../raw_data")

staging_data = []

for recall in raw_usda_json:
    recall_dict = transform_usda_node(recall, states, "../raw_data", "usda_food_safety_recalls.xml")
    staging_data.append(recall_dict)


# Write out USDA Food Safety Recalls as JSON into `transformed_staged_data` folder
# Getting script folder
script_dir = os.path.dirname(__file__)
staged_data_folder_rel_path = "../transformed_staged_data"
staged_data_file_path = os.path.join(script_dir, staged_data_folder_rel_path, "usda_food_safety_recalls_staged.json")

print("Writing out staged USDA JSON")
# Writing out dict as JSON
with open(staged_data_file_path, 'w') as f:
    json.dump(staging_data, f, indent=4, separators=(",", ": "), cls=DateTimeEncoder)
