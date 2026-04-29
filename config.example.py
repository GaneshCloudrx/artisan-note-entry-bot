"""
Configuration template for the bot.

Copy this file to `config.py` and fill in your real values. `config.py` is
gitignored so secrets stay out of source control.
"""

# Feature Toggles - Set to True/False to enable/disable features
LOG_ENABLED = True
LOG_QUEUE_ENABLED = False
RECORDING_ENABLED = False

# Common API Configuration
API_BASE_URL = "https://portal.reuniterx.com/api/v1/"
API_AUTH_HEADER = "Basic <BASE64_OF_USER_COLON_PASSWORD>"
API_SERVER_NAME = "CLDRPA165"
API_BOT_NAME = "Artisan Note Entry BOT"
API_TIMEOUT = 10

# Heartbeat Configuration
HEARTBEAT_ENABLED = True
HEARTBEAT_BASE_URL = "https://portal.reuniterx.com/api/v1/webservice/endpoint/"
HEARTBEAT_AUTH_HEADER = "Basic <BASE64_OF_USER_COLON_PASSWORD>"
HEARTBEAT_SERVER_NAME = "CLDRPA165"
HEARTBEAT_BOT_NAME = "Artisan Note Entry BOT"
HEARTBEAT_TIMEOUT = 10
HEARTBEAT_INTERVAL = 300
HEARTBEAT_ENDPOINT = "rpa_get_bot_status.php"

# Screen Recording Configuration
RECORDING_OUTPUT_DIR = "recordings"
RECORDING_FPS = 5
RECORDING_QUALITY = "medium"
RECORDING_SEGMENT_DURATION = 30

# S3 Upload Configuration (for recordings)
UPLOAD_RECORDING_S3_ENABLED = False
UPLOAD_RECORDING_S3_BUCKET = "your-bucket-name"
UPLOAD_RECORDING_S3_REGION = "us-east-1"
UPLOAD_RECORDING_S3_ACCESS_KEY = ""
UPLOAD_RECORDING_S3_SECRET_KEY = ""
UPLOAD_RECORDING_S3_PREFIX = "bot-recordings/"
UPLOAD_RECORDING_DELETE_AFTER_UPLOAD = True

# API Logging Configuration
API_LOG_ENDPOINT = "https://devc.reuniterx.com/api/v1/webservice/endpoint/rpa_get_bot_status.php"
API_LOG_BATCH_SIZE = 10
API_LOG_BATCH_INTERVAL = 5
API_LOG_ENABLED = True

MACHINE_NAME = "CLDRPA165"
BOT_NAME = "Artisan Note Entry BOT"
ADMIN_EMAIL = "<admin email>"
ADMIN_PASSWORD = "<admin password>"

DEPLOYMENT_STYLE = "DEV"

# Per-note retry policy
MAX_PATIENT_FAILURES = 3

# Error Portal (for max-retry escalation)
ERROR_API_ENDPOINT = "https://portal.reuniterx.com/api/v1/webservice/endpoint/rpa_error_log.php"
ERROR_API_AUTH_USERNAME = "<portal user>"
ERROR_API_AUTH_PASSWORD = "<portal password>"

# CapSolver Configuration (for reCAPTCHA solving)
CAPSOLVER_API_KEY = "<your capsolver api key>"
