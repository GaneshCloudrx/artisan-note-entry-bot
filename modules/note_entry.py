"""
Note Entry Module
Handles adding notes to patient records in Artisan EMR system.
"""

import os
import sys
import time
from datetime import datetime

import system.nova as nova
from playwright.sync_api import Page


class NoteEntry:
    """Class to handle adding notes to patient records in Artisan EMR system."""
    
    def __init__(self, page: Page):
        """
        Initialize NoteEntry class with a Playwright page object.
        
        Args:
            page: Playwright Page object for browser automation
        """
        self.page = page
    
    def open_progress_notes(self) -> bool:
        """
        Open the progress notes section for the selected patient.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            nova.log_print(f"NOTE_ENTRY: 0. Closing popup by sending escape key")
            time.sleep(3)
            self.page.keyboard.press("Escape")
            # Step 1: Wait for progress notes button to be clickable
            nova.log_print(f"NOTE_ENTRY: 1. Waiting for progress notes button to be clickable")
            # check for any iframe
            # switch to iframe with id component-1012
            iframe = self.page.frame_locator("#component-1012")
            button = iframe.locator("#button-1027")
            button.wait_for(state="visible", timeout=6000)
            button.click()
            nova.log_print("NOTE_ENTRY: 2. Progress notes opened")
            return True
            
        except Exception as e:
            nova.log_print(f"NOTE_ENTRY: #. Error opening progress notes: {str(e)}")
            return False
    
    def add_new_note(self, note_content: str, digital_signature: str, 
                     screen_shot_path: str, screenshot_name: str) -> bool:
        """
        Add a new note to the patient's record.
        
        Args:
            note_content: Content of the note to add
            digital_signature: Digital signature for saving the note
            screen_shot_path: Directory path to save screenshot
            screenshot_name: Name of the screenshot file
            
        Returns:
            True if note added successfully, False otherwise
        """
        try:
            # Step 1: Wait for notes component frame to be available
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            nova.log_print(f"NOTE_ENTRY: 3. Waiting for notes component frame")
            
            # Wait for frame to be available and use frame_locator
            self.page.wait_for_selector("#component-1013", state="visible", timeout=10000)
            frame_locator = self.page.frame_locator("#component-1013")
            
            # Step 2: Wait for add button to be visible and click it
            nova.log_print(f"NOTE_ENTRY: 4. Waiting for add button to be visible")
            time.sleep(3)
            self.page.keyboard.press("Escape")
            add_button = frame_locator.locator("#add_advance_progress_notes a").first
            add_button.wait_for(state="visible", timeout=10000)
            add_button.click()
            nova.log_print(f"NOTE_ENTRY: 5. Add button clicked")
            
            # Step 3: Wait for note entry component frame to be available
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
            nova.log_print(f"NOTE_ENTRY: 6. Waiting for note entry component frame")
            
            self.page.wait_for_selector("#component-1014", state="visible", timeout=10000)
            frame_locator = self.page.frame_locator("#component-1014")
            
            # Step 4: Wait for category dropdown to be clickable and select category
            # nova.log_print(f"NOTE_ENTRY: 7. Waiting for category dropdown to be clickable")
            # category_dropdown = frame_locator.locator("#mat-select-0").first
            # category_dropdown.wait_for(state="visible", timeout=10000)
            # time.sleep(3)  # Wait for dropdown to be ready
            # category_dropdown.click()
            # nova.log_print(f"NOTE_ENTRY: 8. Category dropdown clicked")
            
            # # Step 5: Wait for dropdown panel to be visible and select CLOUDRX NOTIFICATION
            # nova.log_print(f"NOTE_ENTRY: 9. Waiting for category panel to be visible")
            # panel = frame_locator.locator(".cdk-overlay-pane .mat-select-panel").first
            # panel.wait_for(state="visible", timeout=10000)
            
            # Select CLOUDRX NOTIFICATION option
            # emb_option = frame_locator.locator(
            #     "mat-option:has(span.mat-option-text:has-text('CLOUDRX NOTIFICATION'))"
            # ).first
            # emb_option.wait_for(state="visible", timeout=10000)
            # emb_option.scroll_into_view_if_needed()
            # emb_option.click()
            # nova.log_print(f"NOTE_ENTRY: 10. Category 'CLOUDRX NOTIFICATION' selected")
            
            # Step 6: Close the dropdown panel by pressing Escape
            # time.sleep(1)
            # self.page.keyboard.press("Escape")
            # nova.log_print(f"NOTE_ENTRY: 11. Category dropdown closed")
            
            # Step 7: Wait for Edit button to be clickable and click it
            nova.log_print(f"NOTE_ENTRY: 12. Waiting for Edit button to be clickable")
            edit_btn = frame_locator.locator("button:has-text('Edit')").first
            edit_btn.wait_for(state="visible", timeout=10000)
            edit_btn.scroll_into_view_if_needed()
            edit_btn.click()
            nova.log_print(f"NOTE_ENTRY: 13. Edit button clicked")
            
            # Step 8: Wait for editable content area to be visible and enter note content
            nova.log_print(f"NOTE_ENTRY: 14. Waiting for editable content area to be visible")
            editable = frame_locator.locator("div.cke_wysiwyg_div[contenteditable='true']").first
            editable.wait_for(state="visible", timeout=10000)
            editable.scroll_into_view_if_needed()
            editable.click()
            editable.fill(note_content)
            self.page.keyboard.press("Escape")
            nova.log_print(f"NOTE_ENTRY: 15. Note text entered")
            
            # Step 9: Take screenshot
            screenshot_path = os.path.join(screen_shot_path, screenshot_name)
            self.page.screenshot(path=screenshot_path, full_page=False)
            nova.log_print(f"NOTE_ENTRY: 16. Screenshot taken and saved as {screenshot_name}")
            
            # Step 10: Wait for Save button to be clickable and click it
            nova.log_print(f"NOTE_ENTRY: 17. Waiting for Save button to be clickable")
            save_btn = frame_locator.locator("button:has-text('Save')").first
            save_btn.wait_for(state="visible", timeout=10000)
            save_btn.scroll_into_view_if_needed()
            save_btn.click()
            nova.log_print(f"NOTE_ENTRY: 18. Save button clicked")
            
            # Step 11: Wait for confirmation dialog and enter digital signature
            time.sleep(3)
            nova.log_print(f"NOTE_ENTRY: 19. Waiting for confirmation dialog")
            
            # Wait for swal2-content to be visible
            swal2_content = frame_locator.locator("#swal2-content").first
            next_sibling = swal2_content.locator("xpath=following-sibling::*[1]")
            next_sibling.scroll_into_view_if_needed()
            next_sibling.click()
            next_sibling.fill(digital_signature)
            nova.log_print(f"NOTE_ENTRY: 20. Digital signature entered")
            
            # Step 12: Click submit button
            nova.log_print(f"NOTE_ENTRY: 21. Waiting for submit button to be clickable")
            submit_btn = frame_locator.locator("button.swal2-confirm.swal2-styled").first
            submit_btn.wait_for(state="visible", timeout=10000)
            submit_btn.click()
            nova.log_print(f"NOTE_ENTRY: 22. Note submitted successfully")
            
            return True
            
        except Exception as e:
            line_number = sys.exc_info()[2].tb_lineno
            nova.log_print(f"NOTE_ENTRY: #. Error adding note: {str(e)} at line {line_number}")
            return False

