import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import uuid
import xml.etree.ElementTree as ET
import os
import time
import json

## CUSTOM CLASSES ##
class CustomError(Exception):
    """Your custom error class"""
    def __init__(self, message=None):
        self.message = message
        super().__init__(message)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)

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


def extract_dl_terms(dt_elmnt):
    dt_str = dt_elmnt.string
    if dt_str is None:
        raise TypeError("Data term element was not a one child NavigableString")
    if dt_str == "Company Announcement Date:":
        dt_str_name = "company_announce_dttm"
    elif dt_str == "FDA Publish Date:":
        dt_str_name = "notification_dttm"
    elif dt_str == "Product Type:":
        dt_str_name = "product_type"
    elif dt_str == "Reason for Announcement:":
        dt_str_name = "recall_reason"
    elif dt_str == "Company Name:":
        dt_str_name = "company_name"
    elif dt_str == "Brand Name:":
        dt_str_name = "brand_name"
    elif dt_str == "Product Description:":
        dt_str_name = "product_description"
    else:
        raise ValueError("Data term element value not recognized.")
    return dt_str_name

def extract_dd_terms(dd_elmnt):
    child_count = len(list(dd_elmnt.children))
    child_list = [child.name for child in dd_elmnt] 
    if child_count == 1:
        dd_val = str([gchild for gchild in dd_elmnt.stripped_strings][0])
        if dd_val is None:
            raise TypeError("Single data description element was not a one child NavigableString")
    elif 'time' in child_list:
        time_tag = dd_elmnt.time
        tag_dict_val_dttm = time_tag.attrs.values()
        tag_dttm_str = list(tag_dict_val_dttm)[0]
        format_string = "%Y-%m-%dT%H:%M:%S%z"
        dd_val = datetime.strptime(tag_dttm_str, format_string)
    elif 'div' in child_list:
        item_div_tags = dd_elmnt.find("div", class_="field--item")
        if len(item_div_tags) == 1:
            dd_val = str(item_div_tags.string)
        else:
            dd_val = [str(div_tag.string) for div_tag in item_div_tags]
    elif 'br' in child_list:
        dd_val = [str(gchild) for gchild in dd_elmnt.stripped_strings]
    else:
        raise ValueError("Data description element value not recognized.")
    return dd_val

# These functions handle the three nested loops that look through <p> tags and try to match state names and abbreviations.
# The start from inner-most and go to outer-most
def match_state_names_abbs(state, string):
    match_list = []
    if len(state) == 2:
        state_pattern = f'\\W{state}\\W'
    else:
        state_pattern = state
    p_match = re.search(state_pattern, string)
    if p_match is not None:
        print(f"Found a match for {state} in the string: {string}\n")
        match_list.append(state)
        return match_list
    else:
        return match_list

def run_state_matches(state_list, string):
    match_list = []
    for state in state_list:
        match_list.extend(match_state_names_abbs(state, string))
    return match_list

def search_strings(state_list, string_list):
    match_list = []
    for string in string_list:
        match_list.extend(run_state_matches(state_list, string))
    return match_list

def search_paragraphs(state_list, paragraph_list):
    match_list = []
    for paragraph in paragraph_list:
        string_list = paragraph.strings
        match_list.extend(search_strings(state_list, string_list))
    return match_list

# Function to create FDA food safety recall data dict
def create_fda_dict(url):
    key_list, val_list = extract_fda_recall_data(url)
    time.sleep(1)
    key_title = key_list.pop(15)
    key_list.insert(0, key_title)
    val_title = val_list.pop(15)
    val_list.insert(0, val_title)
    recall_dict = dict(zip(key_list, val_list))
    # Deleting this key/value from the dictionary because I don't see a need for it in the final data
    del recall_dict['product_type']
    print(f"Finished with recall {recall_dict["title"]} at {url}")
    return recall_dict

def change_timezones(dttm, tz_dest):
    NEW_TZ = ZoneInfo(tz_dest)
    dttm_new_tz = dttm.astimezone(NEW_TZ)
    return dttm_new_tz

# Function to extract all data from the URL
def extract_fda_recall_data(url):
    key_list = []
    val_list = []

    page = get_data_from_url(url)

    page_html = page.text

    soup = BeautifulSoup(page_html, "html.parser")

    description_list = soup.find("dl", class_="lcds-description-list--grid")

    # I'm using this datetime in the <meta property="article:published_time"/> object
    # since it seems to be a more accurate actual time the recall is posted on the
    # FDA site instead of the FDA Publish Date date which is just 12:00AM ET of the 
    # listed publish date. 
    
    ## Not using this anymore since it gets updated with new updates to recall page content
    ## and I don't yet want multiple JSON instances of the same recall
    # meta_tag = soup.find('meta', attrs={'property': 'article:published_time'})
    # meta_tag_dttm_str = str(meta_tag.get("content"))
    # format_string = "%a, %m/%d/%Y - %H:%M"
    # meta_notification_dttm = datetime.strptime(meta_tag_dttm_str, format_string)
    # meta_notification_dttm_et = change_timezones(meta_notification_dttm, "America/New_York")
    # meta_notification_dttm_utc = change_timezones(meta_notification_dttm_et, "UTC")

    # I could grab the title from here but I'm getting it from the <title> tag in the RSS XML instead 
    # since I feel like it would be there more consistently and in an easier way to obtain?
    # <h1 class="content-title text-center">RECALL TITLE HERE</h1>
    # NOW done here below:
    title = soup.find("h1", class_="content-title text-center").get_text()

    dl_children = description_list.children

    for child in dl_children:
        if child.name == "dt":
            dt_str = extract_dl_terms(child)
            key_list.append(dt_str)
        elif child.name == "dd":
            dd_item = extract_dd_terms(child)
            val_list.append(dd_item)

    paragraph_list = soup.find_all("p")

    all_state_abb_matches = search_paragraphs(states[0], paragraph_list)
    all_state_name_matches = search_paragraphs(states[1], paragraph_list)

    dedup_state_abb_matches = list(dict.fromkeys(all_state_abb_matches))
    dedup_state_name_matches = list(dict.fromkeys(all_state_name_matches))

    if dedup_state_name_matches:
        matching_indices = [i for i, element in enumerate(states[1]) if element in dedup_state_name_matches]
        addl_matched_state_abbs = [states[0][i] for i in matching_indices]
        dedup_state_abb_matches.extend(addl_matched_state_abbs)

    final_state_abbs = list(dict.fromkeys(dedup_state_abb_matches))

    key_list.append("impacted_states")
    val_list.append(final_state_abbs)

    key_list.append("agency")
    val_list.append("FDA")

    key_list.append("uid")
    fda_uuid = str(uuid.uuid4())
    val_list.append(fda_uuid)

    key_list.append("recall_url")
    val_list.append(url)

    # Keys with empty values because they are only present in USDA FSIS data and not FDA
    key_list.append("notice_id_number")
    val_list.append(None)

    key_list.append("recall_type")
    val_list.append(None)

    key_list.append("risk_level")
    val_list.append(None)

    key_list.append("recall_classification")
    val_list.append(None)

    key_list.append("title")
    val_list.append(title)

    if len(key_list) != len(val_list):
        raise CustomError(f"Key list has a length of {len(key_list)} but the value list has a length of {len(val_list)}.")

    # Replacing FDA Publish Date with <meta property="article:published_time"/> date
    # Not using the meta tag date anymore since it gets updated anytime edits are made to recall page
    # val_list[1] = meta_notification_dttm_utc

    return [key_list, val_list]

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

# Using handmade array of URLs
target_urls = [
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/duda-farm-fresh-foods-inc-issues-advisory-1587-cases-4-in16-oz-bundle-marketside-celery-sticks",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/supplement-manufacturing-partner-inc-issues-recall-dorado-nutrition-brand-spermidine-supplement-10mg",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/may-flower-international-inc-issue-allergy-alert-undeclared-wheat-beijing-soybean-paste",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/recall-reminder-gerber-products-company-previously-recalled-and-discontinued-all-batches-gerberr",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/harvest-nyc-inc-recalls-enoki-mushroom-due-possible-health-risk",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/new-england-village-foods-issues-allergy-alert-undeclared-almonds-19th-hole-snack-mix",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/mauna-loa-macadamia-nut-company-llc-issues-allergy-alert-undeclared-almonds-and-cashews-mauna-loa",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/trader-joes-sesame-miso-salad-salmon-voluntarily-recalled-due-undeclared-milk-allergen",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/food-co-issues-allergy-alert-undeclared-milk-monkfish-liver-ankimo",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/williams-farms-repack-llc-recalls-tomatoes-due-possible-salmonella-contamination",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/ray-mascari-inc-recalls-4-count-vine-ripe-tomatoes-because-possible-health-risk",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/vietti-food-group-issues-allergy-alert-undeclared-soy-15-oz-yellowstone-brown-sugar-molasses-baked",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/east-trading-inc-issues-alert-undeclared-sulfites-licorice-plum",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/new-england-village-foods-issues-allergy-alert-undeclared-almonds-and-sesame-19th-hole-snack-mix",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/advantage-health-matters-inc-recalls-organic-jumbo-pumpkin-seeds-because-possible-health-risk",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/new-grains-gluten-free-bakery-issues-allergy-alert-undeclared-eggs-soy-and-milk-bakery-products",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/fresh-ready-foods-voluntarily-recalls-ready-eat-sandwiches-and-snack-items-sold-arizona-california",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/knockro-issues-allergy-alert-undeclared-almonds-bonya-yogurt-parfaits",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/naturemills-us-inc-issues-allergy-alert-undeclared-wheat-milk-and-sesame-rice-mixes-soups-spice",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/ariana-sweets-inc-issues-allergy-alert-undeclared-sesame-and-wheat-afghani-corn-bread-doda",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/south-asian-food-inc-issues-allergy-alert-undeclared-peanuts-bengal-king-family-pack-vegetable",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/rm-trading-llc-issues-allergy-alert-undeclared-milk-rm-refresher-instant-milk-tea-powder",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/element-112-llc-dba-madelines-patisserie-issues-allergy-alert-undeclared-wheat-croissants-and",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/bedner-growers-inc-recalls-cucumbers-because-possible-health-risk",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/publix-voluntarily-recalls-greenwise-pear-kiwi-spinach-pea-baby-food-pouches-due-lead",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/ukrops-homestyle-foods-announces-recall-due-possible-health-risk",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/big-y-foods-recalls-made-order-subs-wraps-and-paninis-sold-massachusetts-and-connecticut-because",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/new-grains-gluten-free-bakery-issues-allergy-alert-undeclared-eggs-tree-nuts-soy-and-milk-bakery",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/pennrose-farms-issues-recall-whole-cucumbers-because-possible-health-risk",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/walmart-inc-recalls-marketside-fresh-cut-cucumber-slices-select-texas-stores-because-possible-health",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/jfe-franchising-inc-recalls-limited-number-cucumber-products-because-possible-health-risk-0",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/albertsons-companies-voluntarily-recalls-three-store-made-deli-items-containing-recalled-cucumber",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/santa-monica-seafood-voluntarily-recalls-atlantic-salmon-portions-seafood-stuffing-due-undeclared",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/coastal-companies-issues-voluntary-recall-items-fresh-start-cucumbers-due-potential-salmonella",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/supreme-service-solutions-llc-voluntarily-recalls-supreme-vegetable-products-because-possible-health-0",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/isabelles-kitchen-inc-recalls-refrigerated-deli-salads-containing-fresh-cucumbers-because-possible",
    "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/homegrown-family-foods-issues-allergy-alert-undeclared-milk-shore-lunch-oven-style-breader-batter"
               ]

target_urls.reverse()
staging_data = []

for url in target_urls:
    recall_dict = create_fda_dict(url)
    staging_data.append(recall_dict)

# Write out FDA Food Safety Recalls as JSON into `transformed_staged_data` folder
# Getting script folder
script_dir = os.path.dirname(__file__)
staged_data_folder_rel_path = "../transformed_staged_data"
staged_data_file_path = os.path.join(script_dir, staged_data_folder_rel_path, "fda_food_safety_recalls_staged_refill.json")

print("Writing out staged refill FDA JSON")
# Writing out dict as JSON
with open(staged_data_file_path, 'w') as f:
    json.dump(staging_data, f, indent=4, separators=(",", ": "), cls=DateTimeEncoder)
