"""
Screen Recorder - records the entire bot session continuously with 30-minute segments
Supports S3 upload with multipart upload for large files
"""
import time
import threading
import os
from datetime import datetime
from mss import mss
# import numpy as np
import cv2
import config

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


class ScreenRecorder:
    """
    Records screen continuously during bot operation.
    Splits recordings into segments (default 30 minutes) and optionally uploads to S3.
    """
    
    def __init__(self, output_dir="recordings", fps=5, quality="medium", segment_duration_minutes=30):
        """
        Initialize screen recorder.
        
        Args:
            output_dir: Directory to save recordings (default: "recordings")
            fps: Frames per second (default: 5 for smaller files)
            quality: Video quality - "low", "medium", "high" (default: "medium")
            segment_duration_minutes: Duration of each segment in minutes (default: 30)
        """
        self.output_dir = output_dir
        self.fps = fps
        self.quality = quality
        self.segment_duration = segment_duration_minutes * 60  # Convert to seconds
        self.recording = False
        self.frames = []
        self.thread = None
        self.lock = threading.Lock()
        
        # Segment tracking
        self.segment_start_time = None
        self.current_segment = 0
        self.session_start_time = None
        self.current_filename = None
        
        # S3 upload settings
        self.s3_enabled = config.UPLOAD_RECORDING_S3_ENABLED
        self.s3_client = None
        if self.s3_enabled:
            try:
                import boto3
                # Initialize S3 client
                if config.UPLOAD_RECORDING_S3_ACCESS_KEY and config.UPLOAD_RECORDING_S3_SECRET_KEY:
                    self.s3_client = boto3.client(
                        's3',
                        region_name=config.UPLOAD_RECORDING_S3_REGION,
                        aws_access_key_id=config.UPLOAD_RECORDING_S3_ACCESS_KEY,
                        aws_secret_access_key=config.UPLOAD_RECORDING_S3_SECRET_KEY
                    )
                else:
                    # Use default AWS credentials (from ~/.aws/credentials or environment)
                    self.s3_client = boto3.client('s3', region_name=config.UPLOAD_RECORDING_S3_REGION)
                log_print("S3 client initialized for recording uploads", level="TRACE")
            except ImportError:
                log_print("boto3 not installed - S3 upload of recordings disabled", level="WARN")
                self.s3_enabled = False
            except Exception as e:
                log_print(f"Failed to initialize S3 client: {str(e)} - S3 upload of recordings disabled", level="WARN")
                self.s3_enabled = False
        
        # Quality settings for video encoding
        quality_settings = {
            "low": {"fourcc": cv2.VideoWriter_fourcc(*'mp4v'), "bitrate": 1000},
            "medium": {"fourcc": cv2.VideoWriter_fourcc(*'mp4v'), "bitrate": 2000},
            "high": {"fourcc": cv2.VideoWriter_fourcc(*'XVID'), "bitrate": 4000}
        }
        self.video_settings = quality_settings.get(quality, quality_settings["medium"])
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
        
        log_print(f"Screen recorder initialized (FPS: {self.fps}, Quality: {self.quality}, Segments: {segment_duration_minutes} min)", level="TRACE")
    
    def start_recording(self):
        """Start recording screen in background thread."""
        if self.recording:
            log_print("Recording already in progress", level="TRACE")
            return False
        
        self.recording = True
        self.frames = []
        self.current_segment = 0
        self.session_start_time = datetime.now()
        self.segment_start_time = time.time()
        
        # Start recording thread
        self.thread = threading.Thread(target=self._record_loop, daemon=True)
        self.thread.start()
        
        return True
    
    def stop_recording(self):
        """Stop recording and save final video segment."""
        if not self.recording:
            log_print("No recording in progress", level="TRACE")
            return None
        
        log_print("Stopping screen recording...", level="TRACE")
        
        # Stop recording loop
        self.recording = False
        
        # Wait for thread to finish (with timeout)
        if self.thread:
            self.thread.join(timeout=10)
        
        # Save final segment
        if self.frames:
            try:
                filename = self._save_current_segment()
                log_print(f"Final recording segment saved: {filename}", level="TRACE")
                return filename
            except Exception as e:
                import traceback
                log_print(f"Error saving final recording segment: {str(e)}\n{traceback.format_exc()}", level="ERROR")
                return None
        else:
            log_print("No frames captured - nothing to save", level="TRACE")
            return None
    
    def _record_loop(self):
        """Main recording loop - captures screen frames and manages segments."""
        # Create mss instance in this thread (required for thread-local storage)
        sct = mss()
        
        frame_interval = 1.0 / self.fps
        last_capture_time = time.time()
        
        # Get screen dimensions (primary monitor)
        monitor = sct.monitors[1]  # monitors[0] is all monitors, [1] is primary
        width = monitor["width"]
        height = monitor["height"]
        
        log_print(f"Recording screen: {width}x{height} at {self.fps} FPS", level="TRACE")
        capture_error_logged = False
        
        while self.recording:
            try:
                current_time = time.time()
                
                # Check if segment duration reached
                if current_time - self.segment_start_time >= self.segment_duration:
                    # Save current segment and start new one
                    self._save_and_start_new_segment()
                
                # Capture frame if enough time has passed
                if current_time - last_capture_time >= frame_interval:
                    # Capture screen
                    screenshot = sct.grab(monitor)
                    
                    # Convert to numpy array and then to BGR for OpenCV
                    img = np.array(screenshot)
                    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    
                    # Store frame
                    with self.lock:
                        self.frames.append(img.copy())
                    
                    last_capture_time = current_time
                    capture_error_logged = False
                else:
                    # Sleep a bit to avoid busy waiting
                    time.sleep(0.01)
                    
            except Exception as e:
                # Log error but continue recording; once per run of failing frames
                if not capture_error_logged:
                    log_print(f"Error capturing frame: {str(e)} - recording continues", level="ERROR")
                    capture_error_logged = True
                time.sleep(0.1)
        
        log_print(f"Recording stopped - captured {len(self.frames)} frames in current segment", level="TRACE")
    
    def _save_and_start_new_segment(self):
        """Save current segment and start a new one."""
        with self.lock:
            if not self.frames:
                return
            
            # Save current segment
            filename = self._save_current_segment()
            
            # Upload to S3 if enabled (in background)
            if self.s3_enabled and filename:
                threading.Thread(
                    target=self._upload_to_s3,
                    args=(filename,),
                    daemon=True
                ).start()
            
            # Reset for new segment
            self.frames = []
            self.current_segment += 1
            self.segment_start_time = time.time()
            
            log_print(f"Segment {self.current_segment} saved. Starting segment {self.current_segment + 1}...", level="TRACE")
    
    def _save_current_segment(self):
        """Save current frames to video file."""
        with self.lock:
            if not self.frames:
                return None
            
            # Generate filename for this segment
            session_timestamp = self.session_start_time.strftime("%Y-%m-%d_%H-%M-%S")
            segment_timestamp = datetime.now().strftime("%H-%M-%S")
            self.current_filename = os.path.join(
                self.output_dir,
                f"Bot_Session_{session_timestamp}_part{self.current_segment + 1}_{segment_timestamp}.mp4"
            )
            
            # Get frame dimensions from first frame
            height, width = self.frames[0].shape[:2]
            
            # Create video writer
            fourcc = self.video_settings["fourcc"]
            out = cv2.VideoWriter(
                self.current_filename,
                fourcc,
                self.fps,
                (width, height)
            )
            
            if not out.isOpened():
                raise Exception(f"Failed to open video writer for {self.current_filename}")
            
            # Write all frames
            frames_to_save = self.frames.copy()
            log_print(f"Saving segment {self.current_segment + 1}: {len(frames_to_save)} frames...", level="TRACE")
            
            for i, frame in enumerate(frames_to_save):
                out.write(frame)
                if (i + 1) % 100 == 0:
                    log_print(f"Saved {i + 1}/{len(frames_to_save)} frames...", level="TRACE")
            
            # Release video writer
            out.release()
            
            # Get file size
            file_size_mb = os.path.getsize(self.current_filename) / (1024 * 1024)
            log_print(f"Segment {self.current_segment + 1} saved: {self.current_filename} ({file_size_mb:.2f} MB)", level="TRACE")
            
            return self.current_filename
    
    def _upload_to_s3(self, file_path):
        """Upload file to S3 using multipart upload (for large files)."""
        if not self.s3_client or not os.path.exists(file_path):
            return
        
        try:
            # Generate S3 key (path in bucket)
            filename = os.path.basename(file_path)
            s3_key = f"{config.UPLOAD_RECORDING_S3_PREFIX.rstrip('/')}/{filename}"
            
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            log_print(f"Uploading to S3: {filename} ({file_size_mb:.2f} MB)...", level="TRACE")
            
            # Use boto3's S3Transfer for multipart upload with optimized settings
            from boto3.s3.transfer import TransferConfig, S3Transfer
            
            # Configure multipart upload (5MB chunks, parallel uploads for performance)
            transfer_config = TransferConfig(
                multipart_threshold=5 * 1024 * 1024,  # 5MB - use multipart for files > 5MB
                max_multipart_count=10000,
                multipart_chunksize=5 * 1024 * 1024,  # 5MB chunks
                use_threads=True  # Enable parallel uploads for better performance
            )
            
            # Use S3Transfer for optimized multipart upload
            transfer = S3Transfer(self.s3_client, transfer_config)
            transfer.upload_file(
                file_path,
                config.UPLOAD_RECORDING_S3_BUCKET,
                s3_key
            )
            
            log_print(f"Uploaded to S3: s3://{config.UPLOAD_RECORDING_S3_BUCKET}/{s3_key}", level="TRACE")
            
            # Delete local file if configured
            if config.UPLOAD_RECORDING_DELETE_AFTER_UPLOAD:
                try:
                    os.remove(file_path)
                    log_print(f"Deleted local file after successful upload: {filename}", level="TRACE")
                except Exception as e:
                    log_print(f"Failed to delete local recording {filename} after upload: {str(e)}", level="WARN")
                    
        except Exception as e:
            import traceback
            log_print(f"Error uploading recording to S3: {str(e)}\n{traceback.format_exc()}", level="ERROR")
            # Don't delete file if upload failed
    
    
    def is_recording(self):
        """Check if currently recording."""
        return self.recording
    
    def get_filename(self):
        """Get the current segment filename."""
        return self.current_filename
