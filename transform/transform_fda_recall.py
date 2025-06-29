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
from fake_useragent import UserAgent
from openai import OpenAI
from retry import retry

## GETTING ENVIRONMENT VARIABLES ##
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
def get_latest_browser_version_number(browser, browser_type, operating_system):

    ua = UserAgent()

    all_browsers = ua.data_browsers

    ff_linux_desktop_browsers = [d for d in all_browsers if d['type'] == browser_type and d['os'] == operating_system and d['browser'] == browser]

    latest_ff_browser_num = "0.0"

    for i in ff_linux_desktop_browsers:
        new_num = i["browser_version"]
        if (float(new_num) > float(latest_ff_browser_num)):
            latest_ff_browser_num = new_num
    
    return(latest_ff_browser_num)

def get_data_from_url(url):
    try:
        latest_ff = get_latest_browser_version_number(browser='Firefox', browser_type='desktop', operating_system='Linux')
        ua = f"Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/{latest_ff}"
        headers = {
        'User-Agent': ua
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

def load_json_file(file_name, rel_file_folder_path):
    script_dir = os.path.dirname(__file__)
    data_file_path = os.path.join(script_dir, rel_file_folder_path, file_name)

    with open(data_file_path, "r") as f:
        json_data = json.load(f)
    
    return json_data

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
def create_fda_dict(url, title):
    key_list, val_list = extract_fda_recall_data(url)
    time.sleep(1)
    key_list.insert(0, "title")
    val_list.insert(0, title)
    recall_dict = dict(zip(key_list, val_list))
    # Deleting this key/value from the dictionary because I don't see a need for it in the final data
    del recall_dict['product_type']
    print(f"Finished with recall {recall_dict["title"]} at {url}")
    return recall_dict

def change_timezones(dttm, tz_dest):
    NEW_TZ = ZoneInfo(tz_dest)
    dttm_new_tz = dttm.astimezone(NEW_TZ)
    return dttm_new_tz

# Function to send extracted recall text to OpenAI prompt
@retry(ValueError, tries=3, delay=3)
def classify_recall(recall_text):
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4-turbo-2024-04-09",
        messages=[
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": recall_class_I_example_1,
            },
            {
                "role": "assistant",
                "content": "Class I",
            },
            {
                "role": "user",
                "content": recall_class_II_example_1,
            },
            {
                "role": "assistant",
                "content": "Class II",
            },
            {
                "role": "user",
                "content": recall_class_III_example_1,
            },
            {
                "role": "assistant",
                "content": "Class III",
            },
            {
                "role": "user",
                "content": recall_unk_example_1,
            },
            {
                "role": "assistant",
                "content": "Unknown",
            },
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": recall_class_I_example_2,
            },
            {
                "role": "assistant",
                "content": "Class I",
            },
            {
                "role": "user",
                "content": recall_class_II_example_2,
            },
            {
                "role": "assistant",
                "content": "Class II",
            },
            {
                "role": "user",
                "content": recall_class_III_example_2,
            },
            {
                "role": "assistant",
                "content": "Class III",
            },
            {
                "role": "user",
                "content": recall_unk_example_2,
            },
            {
                "role": "assistant",
                "content": "Unknown",
            },
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": recall_class_I_example_3,
            },
            {
                "role": "assistant",
                "content": "Class I",
            },
            {
                "role": "user",
                "content": recall_class_II_example_3,
            },
            {
                "role": "assistant",
                "content": "Class II",
            },
            {
                "role": "user",
                "content": recall_class_III_example_3,
            },
            {
                "role": "assistant",
                "content": "Class III",
            },
            {
                "role": "user",
                "content": recall_unk_example_3,
            },
            {
                "role": "assistant",
                "content": "Unknown",
            },
            {
                "role": "user",
                "content": recall_text,
            }
        ],
        temperature=0,
    )

    answer = response.choices[0].message.content.strip()

    acceptable_answers = [
        "Class I",
        "Class II",
        "Class III",
        "Unknown",
    ]
    if answer not in acceptable_answers:
        raise ValueError(f"{answer} not in list of acceptable answers")

    return answer

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

    dl_children = description_list.children

    for child in dl_children:
        if child.name == "dt":
            dt_str = extract_dl_terms(child)
            key_list.append(dt_str)
        elif child.name == "dd":
            dd_item = extract_dd_terms(child)
            val_list.append(dd_item)

    paragraph_list = soup.find_all("p")

    combined_p_txt_list = [p.get_text() for p in paragraph_list]
    combined_p_txt_str = ' '.join(combined_p_txt_list)

    recall_classification = classify_recall(combined_p_txt_str)

    if recall_classification == "Class I":
        risk_level = "Potentially High - Class I"
    elif recall_classification == "Class II":
        risk_level = "Potentially Low - Class II"
    elif recall_classification == "Class III":
        risk_level = "Potentially Marginal - Class III"
    elif recall_classification == "Unknown":
        risk_level = "Unknown"
    
    hedge_recall_classification = f"Potentially {recall_classification}"

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
    val_list.append(risk_level)

    key_list.append("recall_classification")
    val_list.append(hedge_recall_classification)

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

# Initial prompt to OpenAI model
prompt = """
You are an AI model trained to classify text.

I will provide the text of a food safety recall issued by the United States Food and Drug Administration.

You will reply with the _classification_ of the recall which denotes the relative degress of health hazard associated with consuming the recalled product.
These are the guidelines to determine the recall class:

- Class I: a situation in which there is a reasonable probability that the use of or exposure to a violative product will cause serious adverse health consequences or death.
- Class II: a situation in which use of or exposure to a violative product may cause temporary or medically reversible adverse health consequences or where the probability of serious adverse health consequences is remote.
- Class III: a situation in which use of or exposure to a violative product is not likely to cause adverse health consequences.

Your reply **must** come from the following list:
- Class I
- Class II
- Class III

If you are _unable_ to make a definitive recall classification determination, you should label it as "Unknown". 
"""

# Recall classification examples used for OpenAI prompting
# Example one url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/homegrown-family-foods-issues-allergy-alert-undeclared-milk-shore-lunch-oven-style-breader-batter
recall_class_I_example_1 = """
Homegrown Family Foods is recalling its Shore Lunch Oven Style Breader & Batter Mix 6oz Box due to the presence of undeclared milk. Individuals with an allergy or severe sensitivity to milk risk serious or life-threatening allergic reactions if they consume this product. For ease of identification, see photo labels below.

The product was primarily distributed in retail stores in Illinois, Indiana, Iowa, Minnesota, Nebraska, New York, North Dakota, Ohio, South Dakota, and Wisconsin between April 29, 2024 and May 1, 2025.

The product comes in 6-ounce (170g) boxes marked with Best By dates of April 23, 2025 through February 25, 2026 and UPC Code 2473912000 and Lots: RP117050, RP120012, RP120011, RP120013, RP123249, RP123389, RP129004, RP129005, RP129006. The Best By date, Lot Code is found on the top of the box and the UPC is found on the bottom of the box.

One illness has been reported to date; the affected individual has recovered.

On 4/23/2025, the firm was notified by a consumer whose daughter had an allergic reaction. The recall was initiated after it was discovered that product containing the milk ingredient was in packaging that did not properly label the presence of milk.

Consumers who have the affected product and have a dairy allergy or sensitivity are urged not to consume the product and to return it to the place of purchase for a full refund.

For questions, consumers may contact Homegrown Family Foods at 706-403-5768 Monday- Friday from 8:00 am to 4:00 pm ET or email QAinquiries@homegrownfamilyfood.com.

This recall is being made with the knowledge of the U.S. Food and Drug Administration.
"""
# Example two url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/supreme-service-solutions-llc-voluntarily-recalls-supreme-vegetable-products-because-possible-health-0
recall_class_I_example_2 = """
Summary of Recall: Supreme Service Solutions LLC. (dba Supreme Produce) is voluntarily recalling items purchased from Bedner Growers Inc. (purchased from Kroger and its affiliates ) due to possible contamination with Salmonella, an organism which can cause serious and sometimes fatal infections in young children, frail or elderly people, and others with weakened immune systems. Healthy persons infected with Salmonella often experience fever, diarrhea (which may be bloody), nausea, vomiting and abdominal pain. In rare circumstances, infection with Salmonella can result in the organism getting into the bloodstream and producing more severe illnesses such as arterial infections (i.e., infected aneurysms), endocarditis and arthritis.

The recalled cucumbers also were sold to a wholesale distributor, which has been directed to further contact its customers with recall instructions. The potential contamination was discovered by Bedner Browers, Inc., who initiated their recall after the US Food and Drug Administration (“FDA”) notified Bedner Browers, Inc. that the cucumbers have been linked by the Food and Drug Administration (FDA) to a Salmonella outbreak that has resulted in 26 illnesses in AL, CA, CO, FL, IL, KS, KY, MI, NC, NY, OH, PA, SC, TN, and VA.

Recalled produce was distributed to Kroger and its affiliated retail stores located in IN, IL, OH, KY, TN, MS, MO, AR and, MI.

Products are packaged in clear-plastic grab-n-go containers of various sizes with the appearance of cut produce.

Retail packaged items and impacted code dates:

Labels Example*: see attached

*Note: Address line will be specific to store of purchase.

There have been no illnesses or consumer complaints reported to date for items purchased from Supreme Produce.

What You Should Do:
Consumers should not consume and discard the product. The product(s) involved is past its shelf life and should already be out of distribution, but if consumers have any product they question, do not consume it, but rather discard it. Consumers with questions or concerns about their health should contact their Physician.

Asking Questions?
Consumers who have purchased the recalled products may obtain additional information by contacting Bedner Growers, Inc. at 866-222-9180, M-F 8:00 a.m. - 5:00 p.m. EDT.

Link to FDA Outbreak Advisory
"""
# Example three url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/fresh-ready-foods-voluntarily-recalls-ready-eat-sandwiches-and-snack-items-sold-arizona-california
recall_class_I_example_3 = """
Fresh & Ready Foods is voluntarily recalling some ready-to-eat sandwiches and snack items sold in Arizona, California, Nevada and Washington. This voluntary recall is being initiated due to possible contamination with Listeria monocytogenes. 

The voluntarily recalled products were distributed between 04/18/2025 and 04/28/2025 in vending and breakroom areas within corporate offices, medical buildings and healthcare facilities located in Arizona, California, Nevada and Washington. This voluntary recall is specifically limited to the products with the “Use By” dates from 4/22/2025 to 05/19/2025 as detailed below.

This issue was identified through environmental monitoring conducted by the FDA during a site inspection, which resulted in a positive finding for Listeria monocytogenes on a piece of equipment. Fresh & Ready Foods has taken immediate corrective actions including removing equipment to address this issue to ensure ongoing food safety and compliance with FDA guidance.

Listeria monocytogenes is an organism that can cause serious and sometimes fatal infections in young children, frail or elderly people, and others with weakened immune systems. Although healthy individuals may suffer only short-term symptoms such as high fever, severe headache, stiffness, nausea, abdominal pain and diarrhea, a Listeria monocytogenes infection can cause miscarriages and stillbirths among pregnant women.

While no illnesses have been reported related to the specific products distributed between 04/18/2025 and 04/28/2025 as listed below, this action is being taken as a precautionary measure to ensure the continued safety of our consumers.

Consumers who may have purchased these items are strongly urged to check the “Use By” date, which is printed clearly on the front of each product package below the “Net Weight”.

Consumers who have this product in their possession are urged to discard any remaining product immediately. Consumers may contact Fresh & Ready Foods at RecallConcern@HotLineGlobal.com or by calling 1-855-424-8390 Monday through Friday 5:00 am – 3:00 pm PST for any questions related to this recall or to request a full refund.

Product labels are attached for identification of products.

This recall is being made with the knowledge of the U.S. Food and Drug Administration.

FDA Advisory

CDC Advisory
"""
# Example one url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/firehook-virginia-issues-allergy-alert-undeclared-sesame-classic-sea-salt-crackers
recall_class_II_example_1 = """
Firehook of Virginia is recalling one lot of Firehook brand Classic Sea Salt Organic Crackers because they may contain undeclared sesame. People who have an allergy or severe sensitivity to sesame run the risk of serious or life-threatening allergic reaction if they consume these products.

The Firehook artisan baked Classic Sea Salt Crackers 8oz come in a clear package with a Best By Date of 09/29/25, and a UPC code 8 99055 00063 5.

The crackers were sold at retail stores in CT, MA, MD, ME, NC, NH, NJ, NY, PA, RI, and VA.

The recall was initiated on 5/30/2025 after it was discovered that the sesame-containing product was distributed in packaging that did not reveal the presence of sesame. Subsequent investigation indicates that the problem was caused by a temporary breakdown in the company’s production and packaging processes causing the wrong labels to be applied to the product.

No illnesses have been reported to date in connection with this problem. Please see the pictures below for further identification.

Consumers who have purchased 8 ounce packages of Firehook brand Classic Sea Salt Crackers with a Best By Date of 9/29/25 are urged to return them to the place of purchase for a full refund. Consumers with questions may contact the company at 1-888-580-0745 Monday – Friday 8:00 am – 4:00 pm EST.
"""
# Example two url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/element-112-llc-dba-madelines-patisserie-issues-allergy-alert-undeclared-wheat-croissants-and
recall_class_II_example_2 = """
Sylvania, Ohio (May 15, 2025) Element 112, LLC dba Madeline’s Pâtisserie is issuing a voluntary recall of a specific batch of our ready-to-eat croissants, due to a labeling error. The ingredient statement on the exterior of the box was labeled as “flour” and does not accurately reflect the contained allergen of “wheat” These products are sold fully baked, frozen, and in a food service case of 24 units.

These products have been produced since March 10, 2025 with the last production date of May 7, 2025. These products were sold to the following locations:

Superior Food Distributors - 4243 Broadmoor Ave SE, Grand Rapids, MI 49512
Carmela Food Distributor - 18350 15 mile Rd, Fraser, MI 48026
Euclid Fish Company - 7839 Enterprise Dr, Mentor, OH 44060
Atlantic Food Distributors - 430 Sixth St. SE, Canton, OH 44702

Products Affected:

2.5oz Chocolate Croissants
3.5oz Chocolate Croissants
2.5oz Raspberry Croissants
3.5oz Raspberry Croissants
Croissant Buns
Issue: Mislabeled ingredient sticker - undeclared allergen (wheat)

Out of an abundance of caution and in compliance with food safety regulations, we ask that you immediately check your inventory and remove any affected product from sale or distribution. If you currently have these affected products, please contact us to arrange for replacement with the correct stickers on the box.

We apologize for the inconvenience and have taken immediate steps to correct the labeling issue to prevent this from happening in the future. Ensuring the safety and trust of our customers is our top priority.

Thank you for your attention to this matter. If you have any questions, please contact Madeline’s Pâtisserie at info@madelinespatisserie.com.
"""
# Example three url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/publix-voluntarily-recalls-greenwise-pear-kiwi-spinach-pea-baby-food-pouches-due-lead
recall_class_II_example_3 = """
LAKELAND, Fla, May 9, 2025 – Publix Super Markets, Inc. has initiated a voluntary recall of GreenWise Pear, Kiwi, Spinach & Pea Baby Food, produced by Bowman Andros LLC and distributed to Publix grocery stores in the company’s eight-state operating area. The product is sold in 4-ounce plastic pouches and has the potential to be contaminated with elevated levels of lead.

This recall is being initiated as a result of routine sampling and is being made with the knowledge of the U.S. Food and Drug Administration.

“As part of our commitment to food safety, potentially impacted products have been removed from all store shelves,” said Publix Director of Communications Maria Brous. “To date, there have been no reported cases of illness. Consumers who have purchased the product in question may return the product to their local store for a full refund. Publix customers with additional questions may call our customer care department toll-free at 1-800-242-1227 or visit our website at publix.comExternal Link Disclaimer.”

Publix, the largest employee-owned company in the U.S. with more than 260,000 associates, currently operates 1,404 stores in Florida, Georgia, Alabama, Tennessee, South Carolina, North Carolina, Virginia and Kentucky. For 28 consecutive years, the company has been recognized by Fortune as a great place to work. In addition, Publix’s dedication to superior quality and customer service is recognized among the top in the grocery business. For more information, visit the company’s newsroom at corporate.publix.com/newsroomExternal Link Disclaimer.
"""
# Example one url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/rm-trading-llc-issues-allergy-alert-undeclared-milk-rm-refresher-instant-milk-tea-powder
recall_class_III_example_1 = """
R&M Trading LLC of Lakewood, WA is recalling approximately 408 packages (1lb. pack per package) and 1624 packages (3/1lb. packs per package) of Instant Milk Tea powder products because they may contain undeclared milk . People who have an allergy or severe sensitivity to milk run the risk of serious or life-threatening allergic reaction if they consume this product.

The R&M Refresher brand Instant Milk Tea products are recalled because the ingredients statement declares Whey and Caseinate in Non-Dairy Creamer ingredients, but it does not specify milk.

The following Instant Milk Tea products are sold in 1lb. plastic pouch on Amazon website between 11/18/2024 and 05/07/2025.

No illnesses have been reported to date.

The recall was initiated after it was discovered during an inspection conducted by the U.S. FDA Office of Global Policy and Strategy in China that products containing milk were distributed in packaging that did not reveal the presence of milk.

Consumers who have purchased affected products are urged not to consume the product and to return it to the place of purchase for a full refund.

Consumers with questions may contact the company at imars.yang@qq.com .

This recall is being made with the knowledge of the U.S. Food and Drug Administration.
"""
# Example two url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/us-trading-company-hayward-ca-recalling-joy-luck-brand-lily-flowers-because-it-may-contain
recall_class_III_example_2 = """
(March 3, 2025) U.S. Trading Company of Hayward, CA is recalling Joy Luck Brand Lily Flowers because it may contain undeclared SULFITES. People who have an allergy or severe sensitivity to sulfites run the risk of serious allergic reaction if they consume these products.

The lily flowers were distributed to retailers Nationwide.

The lily flowers are individually packed in plastic packaging. Below is the product being recalled:

The recall was initiated after Florida Dept of Agriculture and Consumer Services collected a sample of the lily flowers. It was discovered that lily flowers containing sulfites were distributed in packaging that did not reveal the presence of sulfites

No illnesses have been reported to date.

This recall is being made with the knowledge of the U.S. Food and Drug Administration.

Customers with a sulfite allergy or sensitivity who have purchased the affected product are urged not to consume the product and dispose of it or return it to their place of purchase for a full refund.

Consumers with questions may contact U.S. Trading Company at 510-781-1818 Monday thru Friday between 8:00am - 4:30pm PST.
"""
# Example three url: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/urban-spirits-issues-voluntary-recall-urban-spirits-non-alcoholic-drink-mixes-due-potential-under
recall_class_III_example_3 = """
07/02/2024
Urban River Spirits, LLC Urgent Safety Recall
2114 Main St. Forest Grove OR 97116
(503) 475-9765

Dear Consumer,

Urban River Spirits is issuing a voluntary recall of the products listed below due to additional shelf stability testing requirements from the Oregon Department of Agriculture. This recall is being conducted due to a potential safety concern. To date, we have not received any reports of illnesses related to these products. Customers who may have purchased this product on or before 07/02/2024 are urged to return the product for a full refund to Urban River Spirits, LLC at 2114 Main St. Forest Grove OR, 97116, destroy the product, and may contact Michelle Garner Monday - Friday from 8 am to 5 pm at (503) 475-9765 with any questions or concerns. Our goal is to have the testing completed swiftly and timely.

We apologize for any inconvenience this may cause; we want to be transparent with our customers and will do what we can to ensure your safety, which is always our top priority.

Sincerely,
Michelle Garner
Urban River Spirits, LLC
(503) 475-9765
Product Recall
Notice Date: 07/01/2024

**DO NOT CONSUME THIS PRODUCT**

Urban Spirits is issuing a voluntary recall of Urban Spirits non-alcoholic drink mixes due to being produced in an unlicensed and uninspected facility. The product safety is undetermined due to potential under-processing. The product is packaged in 750 mL glass bottles.

The consumption of the recalled product may cause health risks.

** Please return any Urban Spirits non-alcoholic drink mixes to Urban Spirits for a full refund.

* Please contact Michelle Garner at [503-270-9229] between 8:00 am and 5:00 pm PST, M-F for questions /complaints.
"""

recall_unk_example_1 = """
Hot wings, sweet and bold—
Grease kissed lips, a thrill too fast.
Now the night groans loud.
"""
recall_unk_example_2 = """
At the buffet, I heaped up my plate,
From curry to crab, I felt great.
But by evening’s slow creep,
I was curled in a heap,
Cursing choices I made at that gate.
"""
recall_unk_example_3 = """
Oh pasta, rich with cream and spice,
You tempted me—twice, maybe thrice.
Now fevered, pale, I pay the price,
My stomach roars, not once but twice.
A love betrayed by food so nice.
"""

# More FDA resources
# FDA Recalls data dashboard: https://datadashboard.fda.gov/oii/cd/recalls.htm
# FDA's Recall Weekly Enforcement Report: https://www.accessdata.fda.gov/scripts/ires/index.cfm
# FDA 101: Product Recalls https://www.fda.gov/consumers/consumer-updates/fda-101-product-recalls
# FDA Enforcement Report page: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/enforcement-reports
# FDA Recalls Background and Definitions: https://www.fda.gov/safety/industry-guidance-recalls/recalls-background-and-definitions 

## ACTUAL SCRIPT ##

# Read in and parse FDA Food Safety Recalls RSS XML
# Getting script folder
script_dir = os.path.dirname(__file__)
xml_data_folder_rel_path = "../raw_data"
xml_data_file_path = os.path.join(script_dir, xml_data_folder_rel_path, "fda_food_safety_recalls.xml")

tree = ET.parse(xml_data_file_path)
root = tree.getroot()

staging_data = []

full_clean_json = load_json_file("food_safety_recalls.json", "../clean_data")
full_clean_url_list = [recall["recall_url"] for recall in full_clean_json if "recall_url" in recall]

for item in root.iterfind(".//item"):
    recall_title = item.find("title").text.strip()
    recall_url = item.find("guid").text.strip()
    # The below is not needed anymore since it's the exact same as
    # the FDA Publish Date: on the page
    # recall_pub_dttm_str = item.find("pubDate").text
    # format_string = "%a, %d %b %Y %H:%M:%S %Z"
    # recall_pub_dttm = datetime.strptime(recall_pub_dttm_str, format_string)
    if recall_url not in full_clean_url_list:
        recall_dict = create_fda_dict(recall_url, recall_title)
        staging_data.append(recall_dict)

if not staging_data:
    print("No new FDA data to add to the staging file.")
else:
    # Write out FDA Food Safety Recalls as JSON into `transformed_staged_data` folder
    # Getting script folder
    script_dir = os.path.dirname(__file__)
    staged_data_folder_rel_path = "../transformed_staged_data"
    staged_data_file_path = os.path.join(script_dir, staged_data_folder_rel_path, "fda_food_safety_recalls_staged.json")

    print("Writing out staged FDA JSON")
    # Writing out dict as JSON
    with open(staged_data_file_path, 'w') as f:
        json.dump(staging_data, f, indent=4, separators=(",", ": "), cls=DateTimeEncoder)