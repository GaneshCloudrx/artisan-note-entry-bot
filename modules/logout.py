"""
Logout Module
Handles logout functionality for Artisan EMR system.
"""

import time
import system.nova as nova
from playwright.sync_api import Page


class Logout:
    """Class to handle logout operations for Artisan EMR system."""
    
    def __init__(self, page: Page):
        """
        Initialize Logout class with a Playwright page object.
        
        Args:
            page: Playwright Page object for browser automation
        """
        self.page = page
    
    def logout(self) -> bool:
        """
        Perform logout from the Artisan EMR system.
        
        Returns:
            True if logout successful, False otherwise
        """
        try:
            # Step 1: Wait for notes component frame to be available
            self.page.wait_for_load_state("domcontentloaded", timeout=60000)
            nova.log_print(f"LOGOUT: 1. Waiting for notes component frame")
            
            # Step 2: Use frame_locator to access notes frame
            self.page.wait_for_selector("#component-1013", state="visible", timeout=20000)
            frame_locator = self.page.frame_locator("#component-1013")
            
            # Step 3: Wait for system settings button to be visible and click it
            nova.log_print(f"LOGOUT: 2. Waiting for system settings button to be visible")
            system_settings_btn = frame_locator.locator("#system_settings").first
            system_settings_btn.wait_for(state="visible", timeout=60000)
            system_settings_btn.click()
            time.sleep(1)
            nova.log_print(f"LOGOUT: 3. System settings button clicked")
            
            # Step 4: Wait for logout menu item to be clickable and click it
            nova.log_print(f"LOGOUT: 4. Waiting for logout menu item to be clickable")
            logout_item = self.page.locator(
                "div.x-menu-item span.x-menu-item-text:has-text('Logout')"
            ).first
            logout_item.wait_for(state="visible", timeout=60000)
            logout_item.scroll_into_view_if_needed()
            logout_item.click()
            nova.log_print(f"LOGOUT: 5. Logout menu item clicked")
            
            # Step 5: Wait for page to load after logout
            self.page.wait_for_load_state("domcontentloaded", timeout=60000)
            nova.log_print(f"LOGOUT: 6. Logged out successfully")
            
            return True
            
        except Exception as e:
            nova.log_print(f"LOGOUT: #. Error logging out: {str(e)}")
            return False

