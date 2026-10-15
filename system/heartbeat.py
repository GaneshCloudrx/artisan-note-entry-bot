"""
Heartbeat module - sends heartbeat to API and handles remote control (pause/resume)
"""
import threading
import requests

# Simple print function - will be replaced by logger when initialized
def _log_print(message, level=None):
    """Fallback print function - logger will override this"""
    try:
        from system.logger import mask_phi
        message = mask_phi(message)
    except Exception:
        pass
    print(f"[{level or 'TRACE'}] {message}")

# This will be set by helper module when logger is initialized
log_print = _log_print


class HeartbeatManager:
    """
    Manages heartbeat API calls and remote control (pause/resume).
    Heartbeats are sent on demand; each response updates the active status.
    """
    
    def __init__(self, api_url, auth_header, server_name, bot_name, timeout=3):
        """
        Initialize HeartbeatManager.
        
        Args:
            api_url: API endpoint URL
            auth_header: Authorization header value (e.g., "Basic Y2xvdWQ6Q2xvdWRAMjAyMzQ=")
            server_name: Server name for API payload
            bot_name: Bot name for API payload
            timeout: API request timeout in seconds (default: 3)
        """
        self.api_url = api_url
        self.auth_header = auth_header
        self.server_name = server_name
        self.bot_name = bot_name
        self.timeout = timeout
        
        self.lock = threading.Lock()
        self.is_active = True  # Default to active — only pause on explicit active=0
        self.last_error = None
        self.last_successful_response = False
    
    def is_bot_active(self):
        """
        Check if bot should be active (thread-safe).
        Returns: True if bot should run, False if paused
        """
        with self.lock:
            return self.is_active

    def send(self):
        """Send one heartbeat and refresh pause/resume state from the response."""
        try:
            self._send_heartbeat()
        except Exception as e:
            self.last_error = str(e)
    
    def _send_heartbeat(self):
        """Send heartbeat to API and update active status based on response.
        Only pauses if we get a valid response with active == 0.
        On errors (403, timeout, etc.), the current state is preserved.
        """
        payload = {
            "server_name": self.server_name,
            "bot_name": self.bot_name
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.auth_header
        }
        
        got_valid_response = False
        new_active_state = False
        
        try:
            # POST to API with timeout (non-blocking)
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            
            # Check if we got HTTP 200
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # Check if response has expected structure
                    if isinstance(data, dict) and "code" in data and "data" in data:
                        if data.get("code") == 200:
                            data_obj = data.get("data", {})
                            got_valid_response = True
                            if isinstance(data_obj, dict) and "active" in data_obj:
                                active_status = data_obj.get("active", 0)
                                new_active_state = (active_status != 0)
                            else:
                                new_active_state = True
                            self.last_error = None  # Clear error on success
                        else:
                            # code != 200
                            self.last_error = f"API returned code {data.get('code')} (expected 200)"
                    else:
                        # Invalid response structure
                        self.last_error = "Invalid response structure (missing 'code' or 'data')"
                    
                except (ValueError, TypeError) as e:
                    # Invalid JSON or wrong data type
                    self.last_error = f"Invalid response format: {str(e)}"
            else:
                # Non-200 HTTP status code
                self.last_error = f"API returned HTTP status {response.status_code} (expected 200)"
                
        except requests.exceptions.Timeout:
            # Timeout - no valid response
            self.last_error = "API request timeout"
        except requests.exceptions.RequestException as e:
            # Network error - no valid response
            self.last_error = f"API request failed: {str(e)}"
        except Exception as e:
            # Any other unexpected error
            self.last_error = f"Unexpected error: {str(e)}"
        
        # Update state based on whether we got a valid response
        with self.lock:
            old_state = self.is_active
            
            if got_valid_response:
                # Got valid response - update state based on active status
                self.is_active = new_active_state
                self.last_successful_response = True
                
                # Log state changes
                if old_state != new_active_state:
                    if new_active_state:
                        log_print("Bot activated by server (resuming)", level="INFO")
                    else:
                        log_print("Bot paused by server (waiting for activation)", level="WARN")
            else:
                # Invalid/error response — keep current state, don't pause
                self.last_successful_response = False
