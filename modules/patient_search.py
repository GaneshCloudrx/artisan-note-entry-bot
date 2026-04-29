"""
Patient Search Module
Handles patient search functionality in Artisan EMR system.
"""

import sys
import time
import system.nova as nova
from playwright.sync_api import Page


class PatientSearch:
    """Class to handle patient search operations in Artisan EMR system."""
    
    def __init__(self, page: Page):
        self.page = page
    
    def navigate_to_clinical_info(self) -> bool:
        """
        Navigate to Clinical Info section.
        
        Returns:
            True if navigation successful, False otherwise
        """
        try:
            nova.log_print("PATIENT_SEARCH: 1. Waiting for Clinical Info element to be visible")
            clinical_info = self.page.wait_for_selector("#ext-element-21", state="visible", timeout=10000)
            
            clinical_info.click()
            nova.log_print("PATIENT_SEARCH: 2. Clinical Info clicked")
            
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            nova.log_print("PATIENT_SEARCH: 3. Page loaded")
            
            return True
            
        except Exception as e:
            nova.log_print(f"PATIENT_SEARCH: #. Error navigating to clinical info: {str(e)}")
            return False
    
    def search_patient(self, patient_full_name: str, patient_dob: str):
        """
        Search for a patient by typing "LastName, FirstName" into the search box,
        then cycling through dropdown rows with arrow-down + tab to auto-populate
        details, and matching on DOB.

        Args:
            patient_full_name: "LastName, FirstName" format
            patient_dob: Patient DOB in "MM/DD/YY" format

        Returns:
            tuple: (True, 1) if patient found, (False, 0) otherwise
        """
        max_rows = 3

        try:
            # Step 1: Wait for the component frame
            nova.log_print("PATIENT_SEARCH: 4. Waiting for component frame")
            self.page.wait_for_selector("#component-1012", state="visible", timeout=20000)
            frame_locator = self.page.frame_locator("#component-1012")

            # Step 2: Wait for patient search field
            nova.log_print("PATIENT_SEARCH: 5. Waiting for patient search field")
            patient_search_field = frame_locator.locator("#select_patient_new-inputEl")
            patient_search_field.wait_for(state="visible", timeout=10000)

            # Step 3: Build search text - LastName, FirstName (strip special chars from first name)
            first_name_clean = patient_full_name.split(", ")[-1] if ", " in patient_full_name else ""
            for ch in [",", '"', "'"]:
                first_name_clean = first_name_clean.split(ch)[0]
            last_name = patient_full_name.split(", ")[0] if ", " in patient_full_name else patient_full_name
            search_text = f"{last_name}, {first_name_clean}".strip()

            nova.log_print(f"PATIENT_SEARCH: 6. Typing search text: '{search_text}'")
            patient_search_field.scroll_into_view_if_needed()
            patient_search_field.click()
            patient_search_field.fill(search_text)

            # Step 4: Wait for dropdown results to populate
            nova.log_print("PATIENT_SEARCH: 7. Waiting 4s for search results to populate...")
            time.sleep(4)

            # DOB prefix for matching (first 5 chars = "MM/DD")
            dob_prefix = patient_dob[:5] if patient_dob and len(patient_dob) >= 5 else ""
            nova.log_print(f"PATIENT_SEARCH: 8. Will match DOB prefix: '{dob_prefix}'")

            # Step 5: Loop through rows - press down arrow, then tab to auto-populate
            for row_idx in range(max_rows):
                nova.log_print(f"PATIENT_SEARCH: 9. Row {row_idx + 1}/{max_rows} - pressing ArrowDown")
                patient_search_field.press("ArrowDown")
                time.sleep(0.5)

                nova.log_print(f"PATIENT_SEARCH: 10. Row {row_idx + 1}/{max_rows} - pressing Tab to populate details")
                patient_search_field.press("Tab")
                time.sleep(2)

                # Scrape the auto-populated text from the search field
                populated_text = patient_search_field.input_value()
                nova.log_print(f"PATIENT_SEARCH: 11. Row {row_idx + 1}/{max_rows} - populated text: '{populated_text}'")

                # Check if DOB prefix is in the populated details
                if dob_prefix and dob_prefix in populated_text:
                    nova.log_print(f"PATIENT_SEARCH: 12. DOB match found on row {row_idx + 1} - patient selected")
                    self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                    return True, 1
                else:
                    nova.log_print(f"PATIENT_SEARCH: 12. Row {row_idx + 1} - DOB '{dob_prefix}' not found in '{populated_text}', trying next...")
                    # Click back into the field to continue searching
                    patient_search_field.click()
                    patient_search_field.fill(search_text)
                    time.sleep(2)

            nova.log_print(f"PATIENT_SEARCH: 13. No DOB match found after {max_rows} rows")
            return False, 0

        except Exception as e:
            line_number = sys.exc_info()[2].tb_lineno
            nova.log_print(f"PATIENT_SEARCH: #. Error searching for patient: {str(e)} at line {line_number}")
            return False, 0
