"""
Main Bot Script
Automates EMR note entry process for multiple clinics using Playwright.
"""

import sys
import time
from datetime import datetime

import pandas as pd
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import modules.helper as helper
import system.nova as nova
from config import DEPLOYMENT_STYLE, MAX_PATIENT_FAILURES
from modules.api_integration import log_error_to_portal
from modules.browser_manager import BrowserManager
from modules.data_from_api import note_data_from_api, update_api
from modules.login import Login
from modules.logout import Logout
from modules.note_entry import NoteEntry
from modules.patient_search import PatientSearch
from modules.users import get_users

# Clinics that require the "Confidential" checkbox to be ticked on every
# note before saving. Matched case-insensitively against clinic['Clinic_Name'].
CLINICS_REQUIRING_CONFIDENTIAL = {
    "specialists in reproductive medicine & surgery, p.a.",
}


def main():
    """
    Main function - initialize all components and run bot logic.
    """
    # Step 1: Initialize all components (logger, heartbeat, recording) based on config
    nova.initialize()

    nova.log_print("Bot started", level="INFO")

    try:
        # Step 2: Wait for bot to be activated (if heartbeat is enabled)
        nova.check_and_wait_if_paused()

        # Step 3: Initialize browser manager and directories
        nova.log_print("Starting main bot loop...", level="TRACE")
        browser_manager = BrowserManager()
        paths = browser_manager.initialize_directories()
        screen_shot_path = paths['screen_shot_path']

        # Main processing loop
        while True:
            # Step 4: Check if bot should be paused (respects heartbeat if enabled)
            nova.check_and_wait_if_paused()

            # Step 5: Fetch clinics and notes from API
            nova.log_print("Fetching clinics and notes from API...", level="TRACE")
            clinics = get_users()
            notes = note_data_from_api()

            # Step 6: Prepare DataFrames and filter notes by EMR system
            notes = pd.DataFrame() if notes is None else notes
            if notes.empty:
                nova.log_print("No notes from API - waiting 300 seconds", level="TRACE")
                time.sleep(300)
                continue
            notes["emr_system"] = [emr_system.lower() for emr_system in notes['emr_system']]
            clinics["EMR_System"] = [emr_system.lower() for emr_system in clinics['EMR_System']]
            notes["clinic_name"] = [clinic_name.lower() for clinic_name in notes['clinic_name']]

            notes = notes[notes['emr_system'].isin(clinics['EMR_System'])].reset_index(drop=True)
            clinics = pd.DataFrame() if clinics is None else clinics

            # Step 6.5: FEATURE 1 - Filter notes via today's patient report
            #   * skip notes that already succeeded
            #   * skip notes that exhausted retries
            #   * mark duplicate-content notes complete via the API
            patient_report, content_keys = helper.load_patient_report()
            notes, skipped = helper.filter_notes_by_report(
                notes, patient_report, content_keys, update_api
            )
            if skipped:
                helper.log_print(
                    f"Skipped {len(skipped)} notes (already processed, max failures reached or duplicate content)",
                    level="TRACE",
                )

            if notes.empty:
                nova.log_print("No notes to process this cycle - waiting 300 seconds", level="TRACE")
                time.sleep(300)
                continue

            # Per-cycle counters (reset each main-loop iteration)
            total_success = 0
            total_fail = 0

            # Step 7: Process each clinic
            for idy, clinic in clinics.iterrows():
                # Extract clinic information
                clinic_name = clinic['Clinic_Name']
                username = clinic['Username']
                password = clinic['Password1']
                digital_signature_input = clinic['Digital_Sig']
                emr_system = clinic['EMR_System']
                nova.log_print(f"Clinic: {clinic_name}: EMR system: {emr_system}", level="TRACE")

                # Step 8: Filter notes for current clinic
                clinic_notes = notes[
                    (notes['clinic_name'] == clinic_name.lower()) &
                    (notes['emr_system'] == emr_system)
                ].reset_index(drop=True)

                nova.log_print(
                    f"Clinic: {clinic_name}: Starting processing clinic ({len(clinic_notes)} notes)",
                    level="INFO" if len(clinic_notes) else "TRACE",
                )

                # Step 9: Process each note for the clinic
                for idx, note in clinic_notes.iterrows():
                    # Extract note information
                    note_data = note.to_dict()
                    note_id = note_data['note_id']
                    note_content = note_data['note']
                    patient_first_name = note_data['patient_first_name'].strip().split(" ")[0].split("-")[0]
                    patient_last_name = note_data['patient_last_name']
                    patient_dob_raw = note_data['patient_dob']
                    nova.log_print(
                        f"Clinic: {clinic_name}: note_id={note_id} ({len(str(note_content))} chars)",
                        level="TRACE",
                    )

                    # FEATURE 2 - Per-note attempt tracking
                    report_key = (
                        f"{note_data['patient_phone']}_{note_data['patient_first_name']}"
                        f"_{note_data['clinic_name']}_{note_data['note_id']}"
                    )
                    try:
                        prior_failures = int(
                            (patient_report.get(report_key) or {}).get('failure_count', 0) or 0
                        )
                    except (TypeError, ValueError):
                        prior_failures = 0
                    current_attempt = prior_failures + 1
                    helper.log_print(
                        f"Attempt {current_attempt}/{MAX_PATIENT_FAILURES} for note_id={note_id} "
                        f"(clinic {clinic_name})",
                        level="TRACE",
                    )

                    # Step 10: Format patient date of birth (for EMR search)
                    try:
                        patient_dob = datetime.strptime(patient_dob_raw, '%m/%d/%Y').strftime('%m/%d/%y')
                    except Exception:
                        patient_dob = None

                    # Step 11: Construct patient full name
                    patient_full_name = patient_last_name + ", " + patient_first_name

                    nova.log_print(f"Clinic: {clinic_name}: Patient: {idx}: Starting note entry...", level="TRACE")

                    # Per-note outcome state
                    note_succeeded = False
                    note_status = 'failed'  # default if anything goes wrong
                    failure_reason = None   # logged once in the post-attempt outcome line
                    portal_updated = False

                    # Step 12: Launch browser and process note
                    playwright, user_data_dir, extension_path = browser_manager.create_browser_context()

                    page = None
                    context = None
                    with playwright as p:
                        context = p.chromium.launch_persistent_context(
                            user_data_dir=user_data_dir,
                            headless=False,
                            channel="msedge",
                            args=[
                                "--disable-blink-features=AutomationControlled",
                                "--start-maximized",
                            ],
                            viewport={"width": 1600, "height": 900}
                        )
                        context.set_default_timeout(60000)

                        page = context.new_page()

                        try:
                            # Step 13: Login to EMR system
                            nova.log_print(f"Clinic: {clinic_name}: Patient: {idx}: LOGIN: Starting login process...", level="TRACE")
                            login_handler = Login(page)

                            if not login_handler.login(
                                url='https://artisancw.com/index.html',
                                username=username,
                                password=password,
                                digital_signature=digital_signature_input
                            ):
                                failure_reason = f"login: {login_handler.last_error or 'failed'}"
                                note_status = 'failed'
                            else:
                                nova.log_print(f"Clinic: {clinic_name}: Patient: {idx}: LOGIN: Login successful", level="TRACE")

                                # Step 14: Navigate to Clinical Info and search for patient
                                patient_search = PatientSearch(page)

                                if not patient_search.navigate_to_clinical_info():
                                    failure_reason = f"navigate to Clinical Info: {patient_search.last_error or 'failed'}"
                                    note_status = 'failed'
                                else:
                                    search_success, match_count = patient_search.search_patient(
                                        patient_full_name, patient_dob
                                    )

                                    if not search_success:
                                        failure_reason = f"patient search: {patient_search.last_error or 'no match'}"
                                        note_status = 'verification_failed'
                                    else:
                                        nova.log_print(
                                            f"Clinic: {clinic_name}: Patient: {idx}: PATIENT_SEARCH: Patient found and selected",
                                            level="TRACE",
                                        )

                                        # Step 15: Open progress notes
                                        note_entry = NoteEntry(page)

                                        if not note_entry.open_progress_notes():
                                            failure_reason = f"open progress notes: {note_entry.last_error or 'failed'}"
                                            note_status = 'failed'
                                        else:
                                            # Step 16: Add note to patient record
                                            screenshot_name = (
                                                f"screenshot_{clinic_name}_{idx}_"
                                                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                            )

                                            require_confidential = (
                                                (clinic_name or "").strip().lower()
                                                in CLINICS_REQUIRING_CONFIDENTIAL
                                            )
                                            if require_confidential:
                                                nova.log_print(
                                                    f"Clinic: {clinic_name}: Patient: {idx}: "
                                                    f"NOTE_ENTRY: This clinic requires the Confidential checkbox.",
                                                    level="TRACE",
                                                )
                                            if note_entry.add_new_note(
                                                note_content=note_content,
                                                digital_signature=digital_signature_input,
                                                screen_shot_path=screen_shot_path,
                                                screenshot_name=screenshot_name,
                                                check_confidential=require_confidential,
                                            ):
                                                nova.log_print(
                                                    f"Clinic: {clinic_name}: Patient: {idx}: NOTE_ENTRY: Note added successfully",
                                                    level="TRACE",
                                                )

                                                # Step 17: Update note status in API
                                                portal_updated = update_api(note_id)
                                                if portal_updated:
                                                    nova.log_print(
                                                        f"Clinic: {clinic_name}: Patient: {idx}: API: Note updated in API",
                                                        level="TRACE",
                                                    )
                                                note_succeeded = True
                                            else:
                                                failure_reason = f"add note: {note_entry.last_error or 'failed'}"
                                                note_status = 'failed'

                            # Step 18: Logout from EMR system (currently disabled)
                            # logout_handler = Logout(page)
                            # if logout_handler.logout():
                            #     nova.log_print(f"Clinic: {clinic_name}: Patient: {idx}: LOGOUT: Logged out successfully")
                            # else:
                            #     nova.log_print(f"Clinic: {clinic_name}: Patient: {idx}: LOGOUT: Logout failed")

                        except PlaywrightTimeoutError as te:
                            line_number = sys.exc_info()[2].tb_lineno
                            failure_reason = f"timeout: {te} at line {line_number}"
                            note_status = 'timeout'
                        except Exception as e:
                            line_number = sys.exc_info()[2].tb_lineno
                            failure_reason = f"error: {e} at line {line_number}"
                            import traceback
                            nova.log_print(f"Traceback: {traceback.format_exc()}", level="TRACE")
                            note_status = 'failed'
                        finally:
                            # Take screenshot on failed attempts >= 2 BEFORE closing the page
                            if (not note_succeeded) and current_attempt >= 2:
                                try:
                                    helper.take_screenshot(
                                        page=page,
                                        prefix=f"note_entry_failed_attempt{current_attempt}"
                                    )
                                except Exception as ss_exc:
                                    nova.log_print(f"Failed to capture failure screenshot: {ss_exc}", level="WARN")

                            # Ensure browser is closed
                            try:
                                if page is not None:
                                    page.close()
                            except Exception:
                                pass
                            try:
                                if context is not None:
                                    context.close()
                            except Exception:
                                pass
                            nova.log_print(f"Clinic: {clinic_name}: Patient: {idx}: Browser closed", level="TRACE")
                            time.sleep(3)

                    # ----- Post-attempt bookkeeping (Feature 1 + Feature 2) -----
                    if note_succeeded:
                        nova.log_print(
                            f"Clinic: {clinic_name}: Note {note_id} entered in Artisan"
                            + ("" if portal_updated else " (portal status update failed)"),
                            level="INFO",
                        )
                        helper.save_patient_to_report(note_data, 'success', 0)
                        patient_report[report_key] = {
                            'status': 'success',
                            'failure_count': '0',
                        }
                        # Track this success for in-cycle duplicate-content detection
                        content_keys.add(
                            f"{note_data.get('patient_first_name','')}_"
                            f"{note_data.get('patient_last_name','')}_"
                            f"{note_data.get('patient_dob','')}_"
                            f"{note_data.get('patient_phone','')}_"
                            f"{note_data.get('note','')}"
                        )
                        total_success += 1
                    else:
                        exhausted = current_attempt >= MAX_PATIENT_FAILURES
                        nova.log_print(
                            f"Clinic: {clinic_name}: Note {note_id} failed "
                            f"(attempt {current_attempt}/{MAX_PATIENT_FAILURES}) at {failure_reason or 'unknown step'}"
                            + (" - all attempts exhausted" if exhausted else " - will retry"),
                            level="ERROR" if exhausted else "WARN",
                        )
                        helper.save_patient_to_report(note_data, note_status, current_attempt)
                        patient_report[report_key] = {
                            'failure_count': str(current_attempt),
                            'status': note_status,
                        }

                        if current_attempt >= MAX_PATIENT_FAILURES:
                            patient_name = (
                                f"{note_data.get('patient_first_name','')} "
                                f"{note_data.get('patient_last_name','')}"
                            ).strip()
                            log_error_to_portal(
                                patient_name=patient_name,
                                patient_dob=note_data.get('patient_dob', ''),
                                clinic_name=note_data.get('clinic_name', clinic_name),
                                emr_system=note_data.get('emr_system', 'ARTISAN'),
                                error_title=(
                                    f"Patient Note Failed - All {MAX_PATIENT_FAILURES} attempts exhausted"
                                ),
                            )
                        total_fail += 1

            # Session summary after all clinics processed this cycle
            helper.log_print(
                f"Session summary: {total_success} success, {total_fail} failed",
                level="INFO" if (total_success or total_fail) else "TRACE",
            )

            # Step 20: Wait before next iteration
            nova.log_print("Waiting 300 seconds before next iteration...", level="TRACE")
            time.sleep(300)

    except KeyboardInterrupt:
        nova.log_print("Bot stopped by user", level="INFO")
    except Exception as e:
        line_number = sys.exc_info()[2].tb_lineno
        import traceback
        nova.log_print(
            f"Bot crashed: {str(e)} at line {line_number}\n{traceback.format_exc()}",
            level="FATAL",
        )
    finally:
        # Step 21: Stop all components (logger, heartbeat, recording)
        nova.stop()


if __name__ == "__main__":
    main()
