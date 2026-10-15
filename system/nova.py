"""
Nova - System helper functions for bot initialization and management

This module provides all the core functionality for managing logger, heartbeat, and recording.
Developers can use this directly (system.nova) or create their own helper wrapper in modules/helper.py
"""

import config
import system.heartbeat as heartbeat_module
import system.screen_recorder as screen_recorder_module
import system.logger as logger_module

# Global instances
logger_manager = None
heartbeat_manager = None
screen_recorder = None


def _init_logger(file_path=None):
    """
    Initialize the logger manager (file logging + API logging).
    Internal function - use initialize() instead.
    
    Args:
        file_path: Optional custom file path. If None, uses date-based filename (log_YYYY-MM-DD.txt)
    
    Returns:
        LoggerManager instance
    """
    global logger_manager
    logger_manager = logger_module.LoggerManager(file_path)
    
    # Set up log_print in sys modules so they can use logger
    heartbeat_module.log_print = logger_manager.log_print
    screen_recorder_module.log_print = logger_manager.log_print
    
    return logger_manager


def _init_log_file(file_path=None):
    """
    Initialize the log file with date-based naming.
    DEPRECATED: Internal function - use initialize() instead.
    
    Args:
        file_path: Optional custom file path. If None, uses date-based filename (log_YYYY-MM-DD.txt)
    """
    _init_logger(file_path)


def _init_log_queue_manager():
    """
    Initialize and start the log queue manager for async API logging.
    DEPRECATED: Internal function - use initialize() instead.
    
    Returns:
        LoggerManager instance or None if disabled
    """
    global logger_manager
    if logger_manager is None:
        _init_logger()
    return logger_manager


def _close_log_file():
    """Close the log file. DEPRECATED: Internal function - use stop() instead."""
    global logger_manager
    if logger_manager:
        logger_manager.close()


def _close_log_queue_manager():
    """Stop the log queue manager and send remaining logs. DEPRECATED: Internal function - use stop() instead."""
    global logger_manager
    if logger_manager:
        logger_manager.close()


def log_print(message, level=None):
    """
    Print to console and write to log file, and add to API queue.
    
    Args:
        message: Message to log
        level: TRACE, INFO, WARN, ERROR or FATAL (see system/logger.py)
    """
    global logger_manager
    if logger_manager:
        logger_manager.log_print(message, level=level)
    else:
        # Fallback to console if logger not initialized
        from system.logger import mask_phi
        print(f"[{level or 'TRACE'}] {mask_phi(message)}")


def init_heartbeat():
    """
    Create the heartbeat manager. Calls are made explicitly via send_heartbeat().
    
    Returns:
        HeartbeatManager instance or None if disabled
    """
    global heartbeat_manager
    
    if not config.HEARTBEAT_ENABLED:
        return None
    
    heartbeat_api_url = config.HEARTBEAT_BASE_URL + config.HEARTBEAT_ENDPOINT
    heartbeat_manager = heartbeat_module.HeartbeatManager(
        api_url=heartbeat_api_url,
        auth_header=config.HEARTBEAT_AUTH_HEADER,
        server_name=config.HEARTBEAT_SERVER_NAME,
        bot_name=config.HEARTBEAT_BOT_NAME,
        timeout=config.HEARTBEAT_TIMEOUT
    )
    return heartbeat_manager


def send_heartbeat():
    """Send one heartbeat and refresh pause/resume state from the response."""
    global heartbeat_manager
    if heartbeat_manager is not None:
        heartbeat_manager.send()


def stop_heartbeat():
    """Drop the heartbeat manager."""
    global heartbeat_manager
    heartbeat_manager = None


def _init_heartbeat():
    """Internal alias - use initialize() / init_heartbeat()."""
    return init_heartbeat()


def _start_recording(output_dir=None, fps=None, quality=None):
    """
    Start screen recording for the entire bot session.
    Internal function - use initialize() instead.
    
    Args:
        output_dir: Directory to save recordings (default: from config)
        fps: Frames per second (default: from config)
        quality: Video quality - "low", "medium", "high" (default: from config)
    
    Returns:
        True if recording started successfully, False otherwise
    """
    global screen_recorder
    
    if not config.RECORDING_ENABLED:
        return False
    
    # Use config defaults if not provided
    if output_dir is None:
        output_dir = config.RECORDING_OUTPUT_DIR
    if fps is None:
        fps = config.RECORDING_FPS
    if quality is None:
        quality = config.RECORDING_QUALITY
    
    try:
        segment_duration = config.RECORDING_SEGMENT_DURATION
        screen_recorder = screen_recorder_module.ScreenRecorder(
            output_dir=output_dir,
            fps=fps,
            quality=quality,
            segment_duration_minutes=segment_duration
        )
        screen_recorder.start_recording()
        return True
    except Exception as e:
        log_print(f"Failed to start screen recording: {str(e)} - continuing without recording", level="ERROR")
        screen_recorder = None
        return False


def _stop_recording():
    """
    Stop screen recording and save the video file.
    Internal function - use stop() instead.
    
    Returns:
        str: Path to saved recording file, or None if no recording was active
    """
    global screen_recorder
    
    if not screen_recorder:
        return None
    
    try:
        recording_file = screen_recorder.stop_recording()
        return recording_file
    except Exception as e:
        log_print(f"Error stopping screen recording: {str(e)}", level="ERROR")
        return None
    finally:
        screen_recorder = None


def _wait_for_activation(heartbeat_manager):
    """
    Wait until bot is activated by server.
    Internal function - use check_and_wait_if_paused() instead.
    Checks every 5 seconds if bot should resume.
    
    Args:
        heartbeat_manager: HeartbeatManager instance
    """
    if not heartbeat_manager:
        return
    
    import time
    while not heartbeat_manager.is_bot_active():
        log_print("Bot paused by server. Waiting for activation...", level="TRACE")
        time.sleep(10)
        heartbeat_manager.send()


def _check_and_wait_if_paused_with_manager(heartbeat_manager):
    """
    Internal helper: Check if bot is paused, and wait if it is.
    
    Args:
        heartbeat_manager: HeartbeatManager instance (can be None if disabled)
    """
    if heartbeat_manager and not heartbeat_manager.is_bot_active():
        _wait_for_activation(heartbeat_manager)


def check_and_wait_if_paused():
    """
    Check if bot should be paused based on heartbeat status.
    If heartbeat is disabled or bot is active, returns immediately.
    If bot is paused, waits until activated.
    
    Call this in your main loop to respect heartbeat pause/resume.
    Uses the global heartbeat_manager instance.
    """
    global heartbeat_manager
    if heartbeat_manager:
        _check_and_wait_if_paused_with_manager(heartbeat_manager)


def initialize():
    """
    Initialize all components based on config settings.
    This is the main initialization function - call this once at the start.
    
    Components initialized based on config:
    - Logger (file + API logging) if LOG_ENABLED or LOG_QUEUE_ENABLED
    - Heartbeat manager if HEARTBEAT_ENABLED
    - Screen recording if RECORDING_ENABLED
    
    Returns:
        dict: Dictionary with initialized components (for reference, but not required)
    """
    global logger_manager, heartbeat_manager, screen_recorder
    
    # Initialize logger manager (handles file logging + API logging based on config)
    logger_manager = _init_logger(None)
    
    # Initialize and start heartbeat manager (if enabled)
    heartbeat_manager = _init_heartbeat()
    
    # Start screen recording (if enabled)
    if config.RECORDING_ENABLED:
        _start_recording()
    
    log_print("Bot components initialized", level="TRACE")
    
    return {
        'logger_manager': logger_manager,
        'heartbeat_manager': heartbeat_manager,
        'screen_recorder': screen_recorder
    }


def stop():
    """
    Stop all initialized components and clean up.
    This is the main cleanup function - call this at the end (in finally block).
    """
    global logger_manager, heartbeat_manager, screen_recorder
    
    log_print("Cleaning up...", level="TRACE")
    
    # Stop screen recording (if it was started)
    if screen_recorder:
        _stop_recording()
    
    # Drop the heartbeat manager (if it was created)
    stop_heartbeat()
    
    # Close logger manager (handles both file and API logging cleanup)
    if logger_manager:
        logger_manager.close()
        logger_manager = None
    
    log_print("Bot components stopped", level="TRACE")

