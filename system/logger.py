"""
Logger module - handles file logging and async API logging
"""
from datetime import datetime, timedelta, timezone
import time
import queue
import threading
import requests
import os
import re
import config
from config import (
    API_BASE_URL, API_AUTH_HEADER, API_SERVER_NAME, API_BOT_NAME, 
    API_TIMEOUT, API_LOG_ENDPOINT, API_LOG_BATCH_SIZE,
    API_LOG_BATCH_INTERVAL, API_LOG_ENABLED, LOG_ENABLED, LOG_QUEUE_ENABLED
)


# === Log-level system ===
# Pick the level from the event, using the same level for that event in every file.
# Pass the level to log_print; infer_level() below is only the fallback for a call
# that forgot one. Only INFO and above go to the portal (config.API_LOG_MIN_LEVEL).
#
# TRACE  Step detail that is not an outcome: element lookups, keystrokes,
#        per-item progress, per-item loop lines, idle "no data" polls, fetch
#        counts, startup details. Written to the local log only.
# INFO   A real outcome worth seeing on the portal: bot started/stopped, clinic
#        or batch processing started, session summary, a verified result.
# WARN   The bot continues: a retry, a recovered exception, a business skip
#        (missing field, already processed), a popup/wizard appearing.
# ERROR  The record, step, clinic or cycle failed: attempts exhausted, app failed
#        to open/restart, login/config failed with no retry left, a portal call
#        failed with no retry, recording failed. Log the stack trace once, here
#        only.
# FATAL  Unrecoverable, or portal data may have been lost.
LOG_LEVELS = {"TRACE": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
_LEVEL_ALIASES = {"WARNING": "WARN", "CRITICAL": "FATAL", "DEBUG": "TRACE", "VERBOSE": "TRACE"}
API_LOG_MIN_LEVEL = getattr(config, "API_LOG_MIN_LEVEL", "INFO")

_FATAL_KW = ["fatal", "unrecoverable", "crash"]
_ERROR_KW = ["error", "exception", "traceback", "failed"]
_WARN_KW = ["warning", "retry", "retrying", "skipping", "not found", "mismatch"]
_INFO_KW = ["success", "started", "stopped", "summary"]


def normalize_level(level):
    """Canonical level name or None if invalid."""
    if level is None:
        return None
    up = str(level).upper().strip()
    up = _LEVEL_ALIASES.get(up, up)
    return up if up in LOG_LEVELS else None


def infer_level(message):
    """Keyword classifier - fallback level for a call that did not pass one."""
    low = str(message).lower()
    for level, keywords in (("FATAL", _FATAL_KW), ("ERROR", _ERROR_KW),
                            ("WARN", _WARN_KW), ("INFO", _INFO_KW)):
        if any(kw in low for kw in keywords):
            return level
    return "TRACE"


def should_send_to_api(level):
    return LOG_LEVELS.get(level, 0) >= LOG_LEVELS.get(normalize_level(API_LOG_MIN_LEVEL) or "INFO", 1)


# === PHI masking (safety net for what is stored on the VM) ===
# Applied to the local log file and the console. The portal upload keeps the
# original message. \b / lookbehinds keep digits inside file names intact.
def _last4(value):
    """Keep the last 4 characters and hide the rest."""
    value = str(value)
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


_PHI_PATTERNS = [
    (re.compile(r"([\w.+-]+)@[\w-]+(?:\.[\w-]+)+"), lambda m: _last4(m.group(1))),
    (re.compile(r"\b((?:MRN|SSN|member|policy|insurance|account|acct|claim|patient[ _]?id)"
                r"\s*(?:id|no|number|#)?\s*[:#=]?\s*)(?=[A-Za-z0-9-]*\d)([A-Za-z0-9-]{4,})",
                re.IGNORECASE),
     lambda m: m.group(1) + _last4(m.group(2))),
    (re.compile(r"\b\d{3}-\d{2}-(\d{4})\b"), lambda m: "****" + m.group(1)),
    (re.compile(r"(?<![\w*])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?(\d{4})\b"),
     lambda m: "****" + m.group(1)),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), lambda m: _last4(m.group(0))),
    (re.compile(r"\b(?:19|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}\b"), lambda m: _last4(m.group(0))),
    (re.compile(r"\b(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:19|20)\d{2}\b"), lambda m: _last4(m.group(0))),
]


def mask_phi(message):
    """Mask email, labelled IDs, SSN, phone and date patterns, keeping the last 4 characters."""
    text = str(message)
    for pattern, replacement in _PHI_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _portal_timestamp(local_text):
    """VM-local log time as US Central. Applied only to the portal payload."""
    fmt = '%Y-%m-%d %H:%M:%S'
    try:
        utc = datetime.strptime(local_text, fmt).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return local_text
    year = utc.year
    # 2:00 AM Central on the second Sunday of March, through 2:00 AM Central
    # on the first Sunday of November.
    start = datetime(year, 3, 1, tzinfo=timezone.utc)
    start = start.replace(day=8 + (6 - start.weekday()) % 7, hour=8)
    end = datetime(year, 11, 1, tzinfo=timezone.utc)
    end = end.replace(day=1 + (6 - end.weekday()) % 7, hour=7)
    offset = timedelta(hours=-5 if start <= utc < end else -6)
    return (utc + offset).strftime(fmt)


def _write_queue_error(error_message):
    """Write a masked [LOG QUEUE ERROR] line to the console and the daily log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    stored = mask_phi(f"[LOG QUEUE ERROR] {error_message}")
    print(f"[ERROR] {stored}")
    try:
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f"log_{datetime.now().strftime('%Y-%m-%d')}.txt")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{timestamp} - ERROR - {stored}\n")
    except Exception:
        pass


def _parse_log_line(line):
    """Split a log file line into (timestamp, level, message), or None if it is not one.

    Current format is "timestamp - LEVEL - message"; lines written before levels
    existed are "timestamp - message" and get an inferred level.
    """
    parts = line.rstrip("\n").split(" - ", 2)
    if len(parts) < 2:
        return None
    timestamp = parts[0].strip()
    try:
        datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    if len(parts) == 3 and parts[1] in LOG_LEVELS:
        return timestamp, parts[1], parts[2].strip()
    message = line.rstrip("\n").split(" - ", 1)[1].strip()
    return timestamp, infer_level(message), message


class LoggerManager:
    """
    Manages file logging and async API logging.
    Handles both file-based logging and batched API log submission.
    """
    
    def __init__(self, file_path=None):
        """
        Initialize LoggerManager.
        
        Args:
            file_path: Optional custom file path. If None, uses date-based filename (log_YYYY-MM-DD.txt)
        """
        self.log_file = None
        self.log_queue_manager = None
        self.file_path = file_path
        
        # Initialize file logging if enabled
        if LOG_ENABLED:
            self._init_log_file()
        
        # Initialize API logging if enabled
        if LOG_QUEUE_ENABLED:
            self._init_log_queue_manager()
    
    def _init_log_file(self):
        """Initialize the log file with date-based naming."""
        # Create logs directory if it doesn't exist
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        
        if self.file_path is None:
            # Generate date-based filename: logs/log_YYYY-MM-DD.txt
            date_str = datetime.now().strftime('%Y-%m-%d')
            self.file_path = os.path.join(log_dir, f"log_{date_str}.txt")
        
        # Open in append mode - creates if doesn't exist, appends if exists
        self.log_file = open(self.file_path, "a", encoding="utf-8")
    
    def _init_log_queue_manager(self):
        """Initialize and start the log queue manager for async API logging."""
        if not LOG_QUEUE_ENABLED:
            return
        
        self.log_queue_manager = LogQueueManager()
        self.log_queue_manager.start()
    
    def log_print(self, message, level=None):
        """
        Print to console and write to log file, and add to API queue.
        
        Args:
            message: Message to log
            level: TRACE, INFO, WARN, ERROR or FATAL. Inferred from the message if omitted.
        """
        original = str(message)
        stored = mask_phi(original)
        resolved = normalize_level(level) or infer_level(original)
        print(f"[{resolved}] {stored}")
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Write masked text to the local file (VM store)
        if self.log_file:
            self.log_file.write(f"{timestamp} - {resolved} - {stored}\n")
            self.log_file.flush()  # Ensure it's written immediately
        
        # Portal queue keeps the original message
        if self.log_queue_manager and should_send_to_api(resolved):
            self.log_queue_manager.add_log(timestamp, original, resolved)
    
    def close(self):
        """Close log file and stop log queue manager."""
        # Stop log queue manager and send remaining logs
        if self.log_queue_manager:
            self.log_queue_manager.stop()
            self.log_queue_manager = None
        
        # Close log file
        if self.log_file:
            self.log_file.close()
            self.log_file = None


class LogQueueManager:
    """
    Manages async API logging using a queue and background thread.
    Sends logs to API in batches without blocking the main code.
    """
    
    def __init__(self):
        self.queue = queue.Queue()
        self.worker_thread = None
        self.running = False
        # Create logs directory if it doesn't exist
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        self.last_sent_line_file = os.path.join(log_dir, "last_sent_line.txt")
        self.batch = []
        self.last_batch_time = time.time()
        
    def start(self):
        """Start the background worker thread"""
        if not LOG_QUEUE_ENABLED:
            return
        
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
        # Send any missed logs from file on startup
        self._send_missed_logs()
    
    def stop(self):
        """Stop the background worker thread and send remaining logs"""
        if not self.running:
            return
        
        self.running = False
        
        # Drain queue and add to batch
        try:
            while not self.queue.empty():
                try:
                    log_entry = self.queue.get_nowait()
                    self.batch.append(log_entry)
                except queue.Empty:
                    break
        except:
            pass
        
        # Send any remaining logs in batch
        if self.batch:
            self._send_batch_to_api()
            self.batch = []
        
        # Give worker thread a moment to finish
        try:
            if self.worker_thread:
                self.worker_thread.join(timeout=2)
        except:
            pass
    
    def add_log(self, timestamp, message, level="INFO"):
        """Add a log message to the queue (non-blocking)"""
        if not LOG_QUEUE_ENABLED:
            return
        
        try:
            self.queue.put_nowait({
                'timestamp': timestamp,
                'message': message,
                'level': level
            })
        except queue.Full:
            # Queue is full, skip this log (don't block)
            pass
    
    def _worker(self):
        """Background worker thread that processes the queue"""
        while self.running:
            try:
                # Collect logs from queue (try to get multiple before checking)
                collected_any = False
                for _ in range(API_LOG_BATCH_SIZE):
                    try:
                        log_entry = self.queue.get(timeout=0.1)
                        self.batch.append(log_entry)
                        collected_any = True
                    except queue.Empty:
                        break
                
                # Check if we should send batch
                should_send = False
                current_time = time.time()
                
                # Send if batch size reached
                if len(self.batch) >= API_LOG_BATCH_SIZE:
                    should_send = True
                
                # Send if time interval reached and we have logs
                elif self.batch and (current_time - self.last_batch_time) >= API_LOG_BATCH_INTERVAL:
                    should_send = True
                
                if should_send:
                    self._send_batch_to_api()
                    self.batch = []
                    self.last_batch_time = current_time
                elif not collected_any:
                    # No logs collected, sleep a bit
                    time.sleep(0.1)
                
            except Exception as e:
                # Don't let errors in worker thread crash the app
                _write_queue_error(f"Error in log queue worker: {str(e)}")
                time.sleep(1)
    
    def _send_batch_to_api(self):
        """Send a batch of logs to the API"""
        if not self.batch:
            return
        
        try:
            payload = {
                "bot_name": API_BOT_NAME,
                "server_name": API_SERVER_NAME,
                "logs": [
                    {
                        "timestamp": _portal_timestamp(log['timestamp']),
                        "level": log.get('level', 'INFO'),
                        "message": log['message']
                    }
                    for log in self.batch
                ]
            }
            
            response = requests.post(
                API_LOG_ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=API_TIMEOUT
            )
            
            if response.status_code == 200:
                # Success
                pass
            else:
                _write_queue_error(f"API log send failed with status {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            # Don't block if API fails - just log to console / local file
            _write_queue_error(f"Failed to send logs to API: {str(e)}")
        except Exception as e:
            _write_queue_error(f"Error sending logs to API: {str(e)}")
    
    def _send_missed_logs(self):
        """Read log file and send any missed logs on startup"""
        # Get current log file path
        log_dir = "logs"
        date_str = datetime.now().strftime('%Y-%m-%d')
        log_file_path = os.path.join(log_dir, f"log_{date_str}.txt")
        
        if not os.path.exists(log_file_path):
            return
        
        # Read last sent line number (format: "YYYY-MM-DD:line_number")
        last_sent_line = 0
        if os.path.exists(self.last_sent_line_file):
            try:
                with open(self.last_sent_line_file, 'r') as f:
                    content = f.read().strip()
                    # Check if format is "date:line_number" or just "line_number" (old format)
                    if ':' in content:
                        stored_date, line_num = content.split(':', 1)
                        # If stored date matches today, use the line number
                        if stored_date == date_str:
                            last_sent_line = int(line_num)
                        # If different date, start from beginning (new day)
                        else:
                            last_sent_line = 0
                    else:
                        # Old format (just line number) - assume it's for today
                        last_sent_line = int(content)
            except:
                # If file is corrupted, start from beginning
                last_sent_line = 0
        
        try:
            # Read log file from last sent line
            with open(log_file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # Get new lines
            new_lines = lines[last_sent_line:]
            
            if not new_lines:
                return
            
            # Parse and send new logs (only levels the portal accepts)
            batch = []
            for line in new_lines:
                parsed = _parse_log_line(line)
                if parsed is None:
                    continue
                timestamp, level, message = parsed
                if not should_send_to_api(level):
                    continue
                batch.append({
                    'timestamp': timestamp,
                    'level': level,
                    'message': message
                })
            
            if batch:
                # Send in batches
                for i in range(0, len(batch), API_LOG_BATCH_SIZE):
                    chunk = batch[i:i + API_LOG_BATCH_SIZE]
                    self.batch = chunk
                    self._send_batch_to_api()
                    self.batch = []
                    time.sleep(0.1)  # Small delay between batches
                
            # Update last sent line with date:line_number format
            with open(self.last_sent_line_file, 'w') as f:
                f.write(f"{date_str}:{len(lines)}")
                    
        except Exception as e:
            _write_queue_error(f"Error sending missed logs: {str(e)}")
    
    def update_last_sent_line(self, line_number):
        """Update the last sent line number with current date"""
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            with open(self.last_sent_line_file, 'w') as f:
                f.write(f"{date_str}:{line_number}")
        except:
            pass
