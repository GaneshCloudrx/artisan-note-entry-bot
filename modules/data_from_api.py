"""
Data from API Module
Handles fetching clinic details, notes, and updating note status from API.
"""

import pandas as pd

import system.nova as nova
from config import ADMIN_EMAIL, ADMIN_PASSWORD, API_BASE_URL, MACHINE_NAME
from modules.api_integration import (
    get_clinic_details,
    get_emr_notes,
    get_login_token,
    update_note_status,
)


def data_from_api():
    """
    Fetch clinic details and notes from API.
    
    Returns:
        tuple: (clinics DataFrame, notes DataFrame) or (None, None) on failure
    """
    try:
        # Step 1: Fetch clinic details from API
        nova.log_print("API DATA: 1. Fetching clinic details")
        clinic_details = get_clinic_details()
        
        if clinic_details:
            clinic_data = clinic_details['data']
            nova.log_print(f"API DATA: 2. Clinic data fetched successfully with {len(clinic_data)} clinics")
            
            # Step 2: Create clinics DataFrame and filter by machine name
            clinics = pd.DataFrame(
                clinic_data,
                columns=[
                    'Clinic_Id', 'Username', 'Password1', 'clinic_name_sf', 'Clinic_Name',
                    'URL', 'Facility', 'Color', 'login_status', 'note_bot_machine',
                    'lamar_bot_machine', 'ins_pulling_bot_machine'
                ]
            )
            clinics = clinics[clinics['note_bot_machine'] == MACHINE_NAME].reset_index(drop=True)
            nova.log_print(f"API DATA: 3. Filtered clinics for machine {MACHINE_NAME} with {len(clinics)} clinics")
            
            if len(clinics) > 0:
                # Step 3: Get authentication token for admin
                nova.log_print("API DATA: 4. Fetching token for admin")
                status, token = get_login_token(API_BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD)
                
                if status:
                    nova.log_print("API DATA: 5. Token fetched successfully")
                    
                    # Step 4: Fetch EMR notes using the token
                    status, note_details = get_emr_notes(API_BASE_URL, token)
                    
                    if status:
                        nova.log_print(f"API DATA: 6. Notes fetched successfully with {len(note_details['data'])} notes")
                        
                        # Step 5: Create notes DataFrame and filter by clinic names
                        notes = pd.DataFrame(
                            note_details['data'],
                            columns=[
                                'note_id', 'patient_id', 'note', 'author', 'created',
                                'patient_first_name', 'patient_last_name', 'patient_dob',
                                'patient_phone', 'clinic_name', 'emr_system',
                                'prescriber_first_name', 'prescriber_last_name',
                                'created_formatted', 'prescriber_name'
                            ]
                        )
                        notes = notes[notes['clinic_name'].isin(clinics['Clinic_Name'])].reset_index(drop=True)
                        nova.log_print(f"API DATA: 7. Notes filtered for clinics with {len(notes)} notes")
                        
                        return clinics, notes
                    else:
                        nova.log_print("API DATA: 6. Failed to fetch notes")
                        return clinics, None
                else:
                    nova.log_print("API DATA: 5. Failed to fetch token")
                    return clinics, None
            else:
                nova.log_print(f"API DATA: 3. No clinics found for machine {MACHINE_NAME}")
                return None, None
        else:
            nova.log_print("API DATA: 1. Failed to fetch clinic details")
            return None, None
            
    except Exception as e:
        nova.log_print(f"API DATA: #. Error in data_from_api: {str(e)}")
        return None, None


def note_data_from_api():
    """
    Fetch patient notes from API without clinic filtering.
    
    Returns:
        DataFrame: Notes DataFrame or None on failure
    """
    try:
        # Step 1: Get authentication token for admin
        nova.log_print("API DATA: 1. Fetching token for admin")
        status, token = get_login_token(API_BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD)
        
        if status:
            nova.log_print("API DATA: 2. Token fetched successfully")
            
            # Step 2: Fetch EMR notes using the token
            status, note_details = get_emr_notes(API_BASE_URL, token)
            
            if status:
                nova.log_print(f"API DATA: 3. Notes fetched successfully with {len(note_details['data'])} notes")
                
                # Step 3: Create notes DataFrame
                notes = pd.DataFrame(
                    note_details['data'],
                    columns=[
                        'note_id', 'patient_id', 'note', 'author', 'created',
                        'patient_first_name', 'patient_last_name', 'patient_dob',
                        'patient_phone', 'clinic_name', 'emr_system',
                        'prescriber_first_name', 'prescriber_last_name',
                        'created_formatted', 'prescriber_name'
                    ]
                )
                nova.log_print(f"API DATA: 4. Notes filtered for clinics with {len(notes)} notes")
                
                return notes
            else:
                nova.log_print("API DATA: 3. Failed to fetch notes")
                return None
        else:
            nova.log_print("API DATA: 2. Failed to fetch token")
            return None
            
    except Exception as e:
        nova.log_print(f"API DATA: #. Error in note_data_from_api: {str(e)}")
        return None


def update_api(note_id):
    """
    Update note status in API after processing.
    
    Args:
        note_id: ID of the note to update
    """
    # Step 1: Get authentication token
    status, token = get_login_token(API_BASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD)
    
    if status:
        nova.log_print(f"API UPDATE: 1. Token fetched successfully")
        
        # Step 2: Update note status
        status, result = update_note_status(token, note_id)
        
        if status:
            nova.log_print(f"API UPDATE: 2. Note status updated successfully")
        else:
            nova.log_print(f"API UPDATE: 2. Failed to update note status")


if __name__ == "__main__":
    data_from_api()

