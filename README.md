# Bot Template

A simple, reusable template for building bots with:
- ✅ **Heartbeat** - Remote control via API (pause/resume)
- ✅ **Recording** - Continuous screen recording
- ✅ **Logging** - File logging + async API logging
- ✅ **Log Queue Manager** - Batched API log submission

## Features

- **Heartbeat Manager**: Sends periodic heartbeats to API and handles remote pause/resume
- **Screen Recorder**: Records entire bot session continuously
- **Logger**: Date-based log files + async API logging with batching
- **Clean Structure**: Easy to extend with your own business logic

## Quick Start

1. **Copy the template** to your project directory

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure** `config.py`:
   - Set your API endpoints
   - Configure heartbeat interval
   - Set recording options
   - Configure logging

4. **Add your bot logic** in `main.py` (replace the example loop)

5. **Run**:
   ```bash
   python main.py
   ```

## Project Structure

```
bot-template/
├── config.py              # Configuration settings
├── main.py                # Main entry point (add your logic here)
├── requirements.txt       # Python dependencies
├── README.md              # This file
└── modules/
    ├── __init__.py
    ├── heartbeat.py       # Heartbeat manager (standalone)
    ├── screen_recorder.py # Screen recorder (standalone)
    ├── logger.py          # Logging + Log Queue Manager
    └── helper.py          # Placeholder for your utility functions
```

## Configuration

Edit `config.py` to configure:

- **API Settings**: Base URL, auth header, server name, bot name
- **Heartbeat**: Interval and endpoint
- **Recording**: Output directory, FPS, quality
- **Logging**: API endpoint, batch size, interval

## Usage

### Basic Pattern

```python
from modules.logger import init_log_file, init_log_queue_manager, log_print
from modules.heartbeat import HeartbeatManager
from modules.screen_recorder import ScreenRecorder

# Initialize
init_log_file()
log_queue_manager = init_log_queue_manager()
heartbeat_manager = HeartbeatManager(...)
heartbeat_manager.start()
screen_recorder = ScreenRecorder(...)
screen_recorder.start_recording()

try:
    # Your bot logic here
    while True:
        if not heartbeat_manager.is_bot_active():
            wait_for_activation(heartbeat_manager)
        # Do your work
finally:
    # Cleanup
    screen_recorder.stop_recording()
    heartbeat_manager.stop()
    close_log_queue_manager()
    close_log_file()
```

### Heartbeat

The heartbeat manager:
- Sends periodic heartbeats to your API
- Checks `active` status from API response
- Pauses bot if `active == 0` or API error
- Resumes when `active == 1`

Use `heartbeat_manager.is_bot_active()` to check if bot should run.

### Recording

Screen recorder automatically:
- Records at specified FPS and quality
- Saves to `recordings/` directory with timestamp
- Runs in background thread (non-blocking)

### Logging

Logger provides:
- **File logging**: Date-based files (`log_YYYY-MM-DD.txt`)
- **API logging**: Async batched submission to API
- **Simple interface**: Just use `log_print("message")`

## Adding Your Logic

1. **Add business logic** in `main.py` (replace the example loop)
2. **Add utility functions** in `modules/helper.py`
3. **Add custom modules** in `modules/` directory as needed

## Notes

- All modules are standalone and can be used independently
- Logger, heartbeat, and recorder all run in background threads
- Proper cleanup on exit (Ctrl+C or exception)
- No business logic dependencies - clean template ready for your code

## License

Use this template freely for your projects.

