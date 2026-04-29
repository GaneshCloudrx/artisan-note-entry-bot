"""
Browser Manager Module
Handles browser initialization and directory setup for the bot using Playwright.
"""

import os
from playwright.sync_api import sync_playwright


class BrowserManager:
    """Class to manage browser initialization and directory setup."""
    
    def __init__(self, base_path: str = None):
        """
        Initialize BrowserManager with base path.
        
        Args:
            base_path: Base directory path (defaults to script directory)
        """
        if base_path is None:
            base_path = os.path.dirname(os.path.abspath(__file__))
            # Go up one level from modules/ to project root
            base_path = os.path.dirname(base_path)
        
        self.base_path = base_path
        self.storage_state_path = None
        self.extension_path = None
        self.user_data_dir = None
        self.screen_shot_path = None
    
    def initialize_directories(self):
        """
        Initialize all required directories and file paths.
        
        Returns:
            dict: Dictionary containing all paths
        """
        # Setup file paths and directories
        self.storage_state_path = os.path.join(self.base_path, "storage_state.json")
        self.extension_path = os.path.join(
            self.base_path,
            "extensions",
            "namdkelfpkkinnehndcknoohfpbfhnen",
            "1.0.21_0"
        )
        self.user_data_dir = os.path.join(self.base_path, "user_data", "Profile 2")
        self.screen_shot_path = os.path.join(self.base_path, "screenshots")
        
        # Create directories if they don't exist
        if not os.path.exists(self.screen_shot_path):
            os.makedirs(self.screen_shot_path)
        
        if not os.path.exists(self.user_data_dir):
            os.makedirs(self.user_data_dir)
        
        if not os.path.exists(self.storage_state_path):
            open(self.storage_state_path, "w").write("{}")
        
        return {
            'storage_state_path': self.storage_state_path,
            'extension_path': self.extension_path,
            'user_data_dir': self.user_data_dir,
            'screen_shot_path': self.screen_shot_path
        }
    
    def create_browser_context(self):
        """
        Create and return a browser context with configured settings.
        Returns the sync_playwright context manager for use with 'with' statement.
        
        Returns:
            tuple: (playwright context manager, user_data_dir, extension_path)
        """
        # Return the context manager and paths for use in main.py
        return sync_playwright(), self.user_data_dir, self.extension_path

