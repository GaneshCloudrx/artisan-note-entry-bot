"""
API Integration Module for ReuniteRx Portal
Handles clinic details, patient notes retrieval, and note verification updates.
"""

import base64
import json

import requests

import config
import system.nova as nova
# Handle imports for both standalone and module usage


# API Configuration
API_BASE_URL = "https://portal.reuniterx.com/api/v1/webservice/endpoint/"
CLINIC_LIST_ENDPOINT = "rpa_get_eivf_bot_clinic_list.php"
PORTAL_API_ENDPOINT = "api.php"  # Main API endpoint for login and data operations

# Authorization header for clinic list API
CLINIC_API_AUTH = "Basic Y2xvdWQ6Q2xvdWRAMjAyMzQ="


def get_clinic_details():
    """
    Get list of clinic details from the ReuniteRx portal.
    
    Returns:
        dict: Parsed JSON response containing clinic details, or None on failure
    """
    url = API_BASE_URL + CLINIC_LIST_ENDPOINT
    
    headers = {
        'Authorization': CLINIC_API_AUTH
    }
    
    try:
        nova.log_print(f"Fetching clinic details from: {url}", level="TRACE")
        response = requests.post(url, headers=headers, data={}, files={})
        response.raise_for_status()
        
        result = response.json()
        nova.log_print(f"Successfully retrieved clinic details", level="TRACE")
        return result
        
    except requests.exceptions.RequestException as e:
        nova.log_print(f"Error fetching clinic details: {str(e)}", level="ERROR")
        return None
    except json.JSONDecodeError as e:
        nova.log_print(f"Error parsing clinic details response: {str(e)}. Raw response: {response.text}", level="ERROR")
        return None

def get_login_token(api_base_url, admin_email, admin_password):
   
    url = api_base_url
    
    # Prepare the JSON data
    data_json = {
        "method": "admin_login",
        "role": 'admin',
        "public_ip": "66.172.59.18",
        "email": admin_email,
        "password": admin_password
    }
    
    # Prepare form data
    form_data = {
        "data": json.dumps(data_json)
    }
    
    try:
        # Make the POST request
        response = requests.post(url, data=form_data, timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Parse the response
        result = response.json()
        
        # Check if login was successful
        if result.get("status") == "Success" and "auth_token" in result and "userData" in result:
            return True, {
                "token": result["auth_token"],
                "userData": result["userData"],
                "user_info": result["user_info"]
            }
        else:
            # Log failed login response
            nova.log_print(f"Portal admin login failed. Response: {json.dumps(result, indent=2)}", level="ERROR")
            return False, {}
            
    except requests.exceptions.RequestException as e:
        nova.log_print(f"Portal admin login request failed: {str(e)}", level="ERROR")
        return False, {}
    except json.JSONDecodeError as e:
        nova.log_print(f"Failed to parse portal admin login response: {str(e)}", level="ERROR")
        return False, {}
    except Exception as e:
        nova.log_print(f"Portal admin login error: {str(e)}", level="ERROR")
        return False, {}

def get_emr_notes(url, login_data):
    
    # Prepare the JSON data
    data_json = {
        "method": "get_emr_notes_needing_verification",
        "data": login_data["userData"],
        "token": login_data["token"]
    }
    
    # Prepare form data
    form_data = {
        "data": json.dumps(data_json)
    }
    
    try:
        # Make the POST request
        response = requests.post(url, data=form_data, timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Parse the response
        try:
            result = response.json()
        except json.JSONDecodeError as e:
            # Log first 500 chars of response
            nova.log_print(f"Failed to parse get notes response: {str(e)}. Response text: {response.text[:500]}", level="ERROR")
            return False, {}
        
        # Check if request was successful
        if result.get("status") == "Success":
            return True, result
        else:
            # Log failed response
            nova.log_print(f"Get notes failed. Response: {json.dumps(result, indent=2)}", level="ERROR")
            return False, {}
            
    except requests.exceptions.RequestException as e:
        nova.log_print(f"Get notes request failed: {str(e)}", level="ERROR")
        return False, {}
    except Exception as e:
        nova.log_print(f"Get notes error: {str(e)}", level="ERROR")
        return False, {}

def update_note_status(login_data, note_id):
    """
    Update note status via API after note has been processed
    
    Args:
        login_data: Login data containing token and userData
        note_id: Note ID to update
    
    Returns:
        tuple: (success: bool, data: dict) - Returns (True, result) if successful, 
               (False, {"needs_token_refresh": True}) if token expired (code: 401), 
               (False, {}) for other failures
    """
    url = config.API_BASE_URL
    
    # Prepare the JSON data
    data_json = {
        "method": "verify_note_in_emr",  # TODO: Update with actual method name
        "data": login_data["userData"],
        "token": login_data["token"],
        "note_id": note_id
    }
    
    # Prepare form data
    form_data = {
        "data": json.dumps(data_json)
    }
    
    try:
        # Make the POST request
        response = requests.post(url, data=form_data, timeout=30)
        response.raise_for_status()
        
        # Parse the response
        try:
            result = response.json()
        except json.JSONDecodeError as e:
            nova.log_print(f"Note {note_id}: failed to parse update note response: {str(e)}. Response text: {response.text[:500]}", level="ERROR")
            return False, {}
        
        # Check if response code is 401 (token expired/invalid)
        if result.get("code") == 401:
            nova.log_print(f"Note {note_id}: update note failed: Token expired or invalid (code: 401)", level="ERROR")
            return False, {"needs_token_refresh": True}
        
        # Check if request was successful
        if result.get("status") == "Success":
            return True, result
        else:
            nova.log_print(f"Note {note_id}: update note failed. Response: {json.dumps(result, indent=2)}", level="ERROR")
            return False, {}
            
    except requests.exceptions.RequestException as e:
        nova.log_print(f"Note {note_id}: update note request failed: {str(e)}", level="ERROR")
        return False, {}
    except Exception as e:
        nova.log_print(f"Note {note_id}: update note error: {str(e)}", level="ERROR")
        return False, {}

def log_error_to_portal(patient_name, patient_dob, clinic_name, emr_system,
                        error_title="Patient Note Failed"):
    """
    Escalate a permanently-failed note to the RPA error portal.

    Sends a POST to config.ERROR_API_ENDPOINT using HTTP Basic Auth built
    from config.ERROR_API_AUTH_USERNAME / config.ERROR_API_AUTH_PASSWORD.

    Args:
        patient_name: Full patient name (e.g. "John Doe").
        patient_dob: Patient date of birth string (as available).
        clinic_name: Clinic name the note belongs to.
        emr_system: EMR system identifier (e.g. "ARTISAN", "eIVF").
        error_title: Short error title.

    Returns:
        bool: True if HTTP 200 received, False otherwise.
    """
    payload = {
        "type": "error",
        "title": error_title,
        "server_name": config.MACHINE_NAME,
        "bot_name": getattr(config, "BOT_NAME", config.API_BOT_NAME),
        "detail": {
            "name": patient_name,
            "dob": patient_dob,
            "clinic": clinic_name,
            "emr": emr_system,
        },
    }

    auth_raw = "{u}:{p}".format(
        u=config.ERROR_API_AUTH_USERNAME,
        p=config.ERROR_API_AUTH_PASSWORD,
    )
    auth_b64 = base64.b64encode(auth_raw.encode("utf-8")).decode("ascii")

    headers = {
        "Authorization": "Basic {token}".format(token=auth_b64),
        "Content-Type": "application/json",
    }

    try:
        nova.log_print(
            "ERROR_PORTAL: Escalating error for patient '{name}' (clinic={clinic}, emr={emr})".format(
                name=patient_name, clinic=clinic_name, emr=emr_system
            ),
            level="TRACE",
        )
        response = requests.post(
            config.ERROR_API_ENDPOINT,
            headers=headers,
            data=json.dumps(payload),
            timeout=config.API_TIMEOUT,
        )
        if response.status_code == 200:
            nova.log_print(
                "ERROR_PORTAL: Failure reported to the error portal (clinic={clinic})".format(clinic=clinic_name),
                level="INFO",
            )
            return True

        nova.log_print(
            "ERROR_PORTAL: Failed with HTTP {code}. Body: {body}".format(
                code=response.status_code, body=response.text[:300]
            ),
            level="ERROR",
        )
        return False
    except requests.exceptions.RequestException as exc:
        nova.log_print("ERROR_PORTAL: Request failed: {err}".format(err=exc), level="ERROR")
        return False
    except Exception as exc:
        nova.log_print("ERROR_PORTAL: Unexpected error: {err}".format(err=exc), level="ERROR")
        return False


# Example usage and testing
if __name__ == "__main__":
    # Test get_clinic_details
    print("=" * 50)
    print("Testing get_clinic_details()...")
    print("=" * 50)
    clinics = get_clinic_details()
    if clinics:
        print(f"Clinic data retrieved: {json.dumps(clinics, indent=2)[:500]}...")
    else:
        print("Failed to get clinic details")
    
    # Note: To test get_patient_notes and update_note_verification,
    # you need to provide valid credentials
    # 
    # Example:
    # test_url = "https://portal.reuniterx.com/api/v1/webservice/endpoint/api.php"
    # test_username = "your_username"
    # test_password = "your_password"
    # 
    # notes = get_patient_notes(test_url, test_username, test_password)
    # if notes:
    #     print(f"Notes: {notes}")
    #
    # result = update_note_verification(test_url, test_username, test_password, "12345")
    # if result:
    #     print(f"Update result: {result}")

