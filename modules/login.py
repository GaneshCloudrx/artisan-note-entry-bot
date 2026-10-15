"""
Login Module
Handles user authentication and login functionality for Artisan EMR system.
Uses CapSolver API for reCAPTCHA v2 token-based solving.
"""

import time
import capsolver
import system.nova as nova
from playwright.sync_api import Page
from config import CAPSOLVER_API_KEY


class Login:
    """Class to handle login operations for Artisan EMR system."""
    
    def __init__(self, page: Page):
        self.page = page
        self.last_error = None  # Reason for the last failed login, logged by the caller
    
    def login(self, url: str, username: str, password: str, digital_signature: str) -> bool:
        """
        Perform login to the Artisan EMR system.
        
        Returns:
            True if login successful, False otherwise
        """
        try:
            # Step 1: Navigate to login page
            nova.log_print(f"LOGIN: 1. Navigating to {url}", level="TRACE")
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Step 2: Wait for page to fully load
            self.page.wait_for_load_state("networkidle", timeout=60000)
            nova.log_print("LOGIN: 2. Page loaded successfully", level="TRACE")
            
            # Step 3: Enter username
            nova.log_print("LOGIN: 3. Waiting for username field to be visible", level="TRACE")
            username_field = self.page.wait_for_selector("#ext-gen1018", state="visible", timeout=60000)
            username_field.fill(username)
            nova.log_print("LOGIN: 4. Username entered", level="TRACE")
            
            # Step 4: Enter password
            nova.log_print("LOGIN: 5. Waiting for password field to be visible", level="TRACE")
            password_field = self.page.wait_for_selector("#ext-gen1019", state="visible", timeout=60000)
            password_field.fill(password)
            nova.log_print("LOGIN: 6. Password entered", level="TRACE")
            
            # Step 5: Handle reCAPTCHA if present
            captcha_solved = self._handle_recaptcha(url)
            if captcha_solved is False:
                nova.log_print("LOGIN: 8. CAPTCHA: could not be solved", level="TRACE")
                return False
            
            # Step 6: Click login button
            nova.log_print("LOGIN: 9. Waiting for login button to be clickable", level="TRACE")
            login_button = self.page.wait_for_selector("#login_btn-btnEl", state="visible", timeout=60000)
            login_button.click()
            nova.log_print("LOGIN: 10. Login button clicked", level="TRACE")
            
            # Step 7: Enter digital signature
            nova.log_print("LOGIN: 11. Waiting for digital signature field to be visible", level="TRACE")
            digital_signature_field = self.page.wait_for_selector("#ext-gen1021", state="visible", timeout=60000)
            digital_signature_field.fill(digital_signature)
            nova.log_print("LOGIN: 12. Digital signature entered", level="TRACE")
            
            # Step 8: Click verify button
            nova.log_print("LOGIN: 13. Waiting for verify digital password button to be clickable", level="TRACE")
            verify_button = self.page.wait_for_selector("#btn_verify_digital_password-btnEl", state="visible", timeout=60000)
            verify_button.click()
            nova.log_print("LOGIN: 14. Verify button clicked", level="TRACE")
            
            # Step 9: Wait for successful login
            nova.log_print("LOGIN: 15. Waiting for login to complete", level="TRACE")
            self.page.wait_for_selector("#ext-treelistitem-2", state="visible", timeout=60000)
            nova.log_print("LOGIN: 16. Login successful", level="TRACE")
            
            return True
            
        except Exception as e:
            self.last_error = str(e)
            nova.log_print(f"LOGIN: #. Error logging in: {str(e)}", level="TRACE")
            return False

    def _handle_recaptcha(self, url: str):
        """
        Handle reCAPTCHA using CapSolver token-based API.
        Solves the captcha on CapSolver's servers and injects the token into the page.

        Returns:
            True  - captcha solved or not present
            False - all retries exhausted
        """
        max_attempts = 3

        # Check if reCAPTCHA is on the page
        try:
            recaptcha_iframe = self.page.wait_for_selector(
                "iframe[title='reCAPTCHA']",
                state="visible",
                timeout=10000
            )
        except Exception:
            nova.log_print("LOGIN: 7. CAPTCHA: No reCAPTCHA found on page - skipping", level="TRACE")
            return True

        if not recaptcha_iframe:
            nova.log_print("LOGIN: 7. CAPTCHA: No reCAPTCHA found - skipping", level="TRACE")
            return True

        # Extract the site key from the iframe src
        iframe_src = recaptcha_iframe.get_attribute("src") or ""
        site_key = self._extract_site_key(iframe_src)
        if not site_key:
            self.last_error = "CAPTCHA site key not found in reCAPTCHA iframe"
            nova.log_print(f"LOGIN: 7. CAPTCHA: Could not extract site key from iframe src: {iframe_src[:150]}", level="TRACE")
            return False

        nova.log_print(f"LOGIN: 7. CAPTCHA: reCAPTCHA detected - site_key={site_key}", level="TRACE")

        if not CAPSOLVER_API_KEY:
            self.last_error = "CAPSOLVER_API_KEY is empty in config.py"
            nova.log_print("LOGIN: 7. CAPTCHA: CAPSOLVER_API_KEY is empty in config.py", level="ERROR")
            return False

        capsolver.api_key = CAPSOLVER_API_KEY

        for attempt in range(1, max_attempts + 1):
            nova.log_print(f"LOGIN: 7a. CAPTCHA: Attempt {attempt}/{max_attempts} - sending to CapSolver", level="TRACE")

            try:
                solution = capsolver.solve({
                    "type": "ReCaptchaV2TaskProxyLess",
                    "websiteURL": url,
                    "websiteKey": site_key,
                })

                token = solution.get("gRecaptchaResponse")
                if not token:
                    nova.log_print(f"LOGIN: 7b. CAPTCHA: Attempt {attempt}/{max_attempts}: CapSolver returned no token: {solution}", level="WARN")
                    continue

                nova.log_print(f"LOGIN: 7b. CAPTCHA: Got token from CapSolver ({len(token)} chars)", level="TRACE")

                # Inject the token into the page
                self._inject_recaptcha_token(token)
                nova.log_print("LOGIN: 8. CAPTCHA: Token injected successfully - captcha solved", level="TRACE")
                return True

            except Exception as e:
                nova.log_print(
                    f"LOGIN: 7b. CAPTCHA: Attempt {attempt}/{max_attempts} failed - {type(e).__name__}: {str(e)[:200]}"
                    + (" - retrying in 3s" if attempt < max_attempts else ""),
                    level="WARN",
                )

            if attempt < max_attempts:
                time.sleep(3)

        self.last_error = f"CAPTCHA not solved after {max_attempts} CapSolver attempts"
        return False

    def _extract_site_key(self, iframe_src: str) -> str:
        """Extract the reCAPTCHA site key from the iframe src URL."""
        try:
            if "k=" in iframe_src:
                key_part = iframe_src.split("k=")[1]
                return key_part.split("&")[0]
        except (IndexError, ValueError):
            pass
        return ""

    def _inject_recaptcha_token(self, token: str):
        """Inject the solved reCAPTCHA token into the page and trigger the callback."""
        self.page.evaluate(f"""() => {{
            // Set the token in the g-recaptcha-response textarea
            const textarea = document.getElementById('g-recaptcha-response');
            if (textarea) {{
                textarea.style.display = 'block';
                textarea.value = '{token}';
                textarea.style.display = 'none';
            }}
            
            // Try to trigger the reCAPTCHA callback
            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                const clients = ___grecaptcha_cfg.clients;
                if (clients) {{
                    for (const key in clients) {{
                        const client = clients[key];
                        // Walk through the client object to find the callback
                        const findCallback = (obj, depth) => {{
                            if (depth > 5 || !obj) return null;
                            for (const k in obj) {{
                                if (typeof obj[k] === 'function' && k === 'callback') {{
                                    return obj[k];
                                }}
                                if (typeof obj[k] === 'object' && obj[k] !== null) {{
                                    const found = findCallback(obj[k], depth + 1);
                                    if (found) return found;
                                }}
                            }}
                            return null;
                        }};
                        const callback = findCallback(client, 0);
                        if (callback) {{
                            callback('{token}');
                            return;
                        }}
                    }}
                }}
            }}
            
            // Fallback: try common global callback names
            if (typeof captchaCallback === 'function') captchaCallback('{token}');
            else if (typeof onRecaptchaSuccess === 'function') onRecaptchaSuccess('{token}');
        }}""")
