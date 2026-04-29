"""
Logger module - handles file logging and async API logging
"""
from datetime import datetime
import time
import queue
import threading
import requests
import os
from config import (
    API_BASE_URL, API_AUTH_HEADER, API_SERVER_NAME, API_BOT_NAME, 
    API_TIMEOUT, API_LOG_ENDPOINT, API_LOG_BATCH_SIZE,
    API_LOG_BATCH_INTERVAL, API_LOG_ENABLED, LOG_ENABLED, LOG_QUEUE_ENABLED
)


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
    
    def log_print(self, message):
        """
        Print to console and write to log file, and add to API queue.
        
        Args:
            message: Message to log
        """
        print(message)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Write to file if enabled
        if self.log_file:
            self.log_file.write(f"{timestamp} - {message}\n")
            self.log_file.flush()  # Ensure it's written immediately
        
        # Add to API queue (non-blocking)
        if self.log_queue_manager:
            self.log_queue_manager.add_log(timestamp, message)
    
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
    
    def add_log(self, timestamp, message):
        """Add a log message to the queue (non-blocking)"""
        if not LOG_QUEUE_ENABLED:
            return
        
        try:
            self.queue.put_nowait({
                'timestamp': timestamp,
                'message': message
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
                print(f"Error in log queue worker: {str(e)}")
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
                        "timestamp": log['timestamp'],
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
                print(f"API log send failed with status {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            # Don't block if API fails - just log to console
            print(f"Failed to send logs to API: {str(e)}")
        except Exception as e:
            print(f"Error sending logs to API: {str(e)}")
    
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
            
            # Parse and send new logs
            batch = []
            for line in new_lines:
                # Parse log line: "2025-11-26 15:04:40 - message"
                parts = line.split(' - ', 1)
                if len(parts) == 2:
                    timestamp = parts[0].strip()
                    message = parts[1].strip()
                    batch.append({
                        'timestamp': timestamp,
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
            print(f"Error sending missed logs: {str(e)}")
    
    def update_last_sent_line(self, line_number):
        """Update the last sent line number with current date"""
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            with open(self.last_sent_line_file, 'w') as f:
                f.write(f"{date_str}:{line_number}")
        except:
            pass

