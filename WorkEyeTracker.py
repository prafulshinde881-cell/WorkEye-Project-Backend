"""
╔═══════════════════════════════════════════════════════════════╗
║                    WORK-EYE TRACKER                           ║
║              Pre-Configured for workeyeprofessional            ║
╠═══════════════════════════════════════════════════════════════╣
║  Company ID: 24                                               ║
║  Token: ***OGxKdw==                                      ║
║  Generated: 2026-02-27 06:25:55 UTC                       ║
╠═══════════════════════════════════════════════════════════════╣
║  INSTRUCTIONS:                                                ║
║  1. Run this file on employee computer                        ║
║  2. Employee enters their registered email                    ║
║  3. Tracker automatically verifies and starts                 ║
╚═══════════════════════════════════════════════════════════════╝
"""

"""
MINIMAL WORK TRACKER - Clean UI Version
========================================
✅ Synced with backend tracker_routes.py
✅ Email verification via /tracker/verify-member
✅ Auto device ID generation and DB storage
✅ Simple UI: Email + PUNCH IN → PUNCH OUT only
"""

import os
import sys
import time
import json
import base64
import psutil
import win32gui
import win32process
import win32api
from PIL import Image, ImageGrab
from datetime import datetime
from io import BytesIO
import requests
from threading import Thread, Lock
import logging
import socket
import getpass
import platform
import tkinter as tk
from tkinter import messagebox
import uuid

# ============================================================================
# CONFIGURATION (Embedded by backend when admin downloads)
# ============================================================================

CONFIG = {
    'config_dir': os.path.join(os.getenv('APPDATA'), 'Tracker'),
    'config_file': None,
    'log_file': None,
    
    # Backend configuration (EMBEDDED BY ADMIN DOWNLOAD)
    'backend_url': 'http://127.0.0.1:10000',
    'tracker_token': 'MjQ6alRCdlI3cGVYRE1jakhxRnQ1SDdIaVYySjA2M2VBYmhMMjA2WlJJOGxKdw==',  # Will be replaced by backend
    'company_id': 24,     # Will be replaced by backend
    
    # Intervals
    'screenshot_interval': 300,
    'activity_check_interval': 5,
    'upload_interval': 30,
    'idle_threshold': 180,
    'heartbeat_interval': 60,
    
    # Runtime data
    'device_id': None,
    'member_email': None,
}

# Setup directories
os.makedirs(CONFIG['config_dir'], exist_ok=True)
CONFIG['log_file'] = os.path.join(CONFIG['config_dir'], 'tracker.log')
CONFIG['config_file'] = os.path.join(CONFIG['config_dir'], 'config.json')

# Logging
# create handlers separately so console output can have a simpler format (no timestamp)
file_handler = logging.FileHandler(CONFIG['log_file'], encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(message)s'))  # mimic print output

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ============================================================================
# CONFIGURATION MANAGER
# ============================================================================

class ConfigurationManager:
    """Fetch and manage dynamic configuration from backend"""
    def __init__(self):
        self.last_sync = 0
        self.sync_interval = 300  # Re-sync every 5 minutes
        self.sync_in_progress = False
    
    def fetch_configuration(self):
        """Fetch configuration from server and update CONFIG"""
        if self.sync_in_progress:
            return False
        
        try:
            self.sync_in_progress = True
            
            if not CONFIG.get('tracker_token'):
                logger.warning("[CONFIG] No tracker token available")
                return False
            
            url = f"{CONFIG['backend_url']}/api/tracker/configuration"
            params = {'device_id': STATE.device_id if hasattr(STATE, 'device_id') else 'unknown'}
            
            logger.info(f"[CONFIG] Fetching configuration from {url}")
            
            response = requests.get(
                url,
                headers={'X-Tracker-Token': CONFIG['tracker_token']},
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    # Update configuration intervals
                    # Backend sends minutes, convert to seconds
                    screenshot_min = data.get('screenshot_interval_minutes', 10)
                    idle_min = data.get('idle_timeout_minutes', 5)
                    
                    CONFIG['screenshot_interval'] = screenshot_min * 60
                    CONFIG['idle_threshold'] = idle_min * 60
                    
                    # Store office hours if needed
                    CONFIG['office_start_time'] = data.get('office_start_time', '09:00:00')
                    CONFIG['office_end_time'] = data.get('office_end_time', '18:00:00')
                    CONFIG['working_days'] = data.get('working_days', [1,2,3,4,5])
                    
                    self.last_sync = time.time()
                    
                    logger.info(f"✅ Configuration synced successfully")
                    logger.info(f"   📸 Screenshot interval: {screenshot_min} min ({CONFIG['screenshot_interval']}s)")
                    logger.info(f"   ⏰ Idle threshold: {idle_min} min ({CONFIG['idle_threshold']}s)")
                    logger.info(f"   🏢 Office hours: {CONFIG['office_start_time']} - {CONFIG['office_end_time']}")
                    logger.info(f"   📅 Working days: {CONFIG['working_days']}")
                    
                    return True
                else:
                    logger.error(f"[CONFIG] Server returned error: {data}")
            else:
                logger.error(f"[CONFIG] HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout:
            logger.error("[CONFIG] Request timeout - server may be slow")
        except requests.exceptions.ConnectionError:
            logger.error("[CONFIG] Connection error - check network and backend URL")
        except Exception as e:
            logger.error(f"[CONFIG] Fetch failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.sync_in_progress = False
        
        return False
    
    def should_sync(self):
        """Check if it's time to re-sync configuration"""
        return (time.time() - self.last_sync) > self.sync_interval
    
    def force_sync(self):
        """Force immediate configuration sync"""
        self.last_sync = 0
        return self.fetch_configuration()

# Initialize configuration manager
config_manager = ConfigurationManager()

# ============================================================================
# GLOBAL STATE
# ============================================================================

class GlobalState:
    def __init__(self):
        self.lock = Lock()
        self.total_seconds = 0.0
        self.active_seconds = 0.0
        self.idle_seconds = 0.0
        self.locked_seconds = 0.0
        self.is_idle = False
        self.is_locked = False
        self.idle_for = 0.0
        self.current_window = ""
        self.current_process = ""
        self.session_start = datetime.now()
        self.punch_in_time = None
        self.last_activity_time = datetime.now()
        self.last_screenshot_time = datetime.now()
        self.windows_opened = []
        self.latest_screenshot_b64 = None
        self.last_mouse_pos = None
        
        # Auto-generate device ID (persistent)
        self.device_id = self._get_or_create_device_id()
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        self.os_info = f"{platform.system()} {platform.release()}"
        
        self.is_tracking = False
    
    def _get_or_create_device_id(self):
        """Get or create persistent device ID"""
        try:
            config_file = os.path.join(os.getenv('APPDATA'), 'Tracker', 'device.json')
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    if data.get('device_id'):
                        return data['device_id']
        except:
            pass
        
        # Generate new device ID
        device_id = str(uuid.uuid4())[:8]
        
        # Save it
        try:
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, 'w') as f:
                json.dump({'device_id': device_id}, f)
        except:
            pass
        
        return device_id
    
    def add_time(self, seconds, is_active, is_idle, is_locked):
        with self.lock:
            self.total_seconds += seconds
            if is_locked:
                self.locked_seconds += seconds
            elif is_idle:
                self.idle_seconds += seconds
            elif is_active:
                self.active_seconds += seconds
    
    def update_activity(self, window, process):
        with self.lock:
            self.current_window = window
            self.current_process = process
            entry = f"{process}||{window}"
            if entry not in self.windows_opened:
                self.windows_opened.append(entry)
                if len(self.windows_opened) > 50:
                    self.windows_opened = self.windows_opened[-50:]
    
    def get_payload(self, include_screenshot=None):
        """Get payload matching backend tracker_routes.py format

        Passing `include_screenshot=None` (the default) will atomically check the
        state under the lock and include the screenshot if one is available. This
        avoids races where the caller tests `STATE.latest_screenshot_b64` outside
        the lock and the value changes before the payload is built.
        """
        with self.lock:
            payload = {
                # Match backend field names exactly
                "deviceid": self.device_id,  # Backend uses 'deviceid'
                "username": self.username,
                "email": CONFIG.get('member_email', ''),
                "hostname": self.hostname,
                "osinfo": self.os_info,  # Backend uses 'osinfo'
                "timestamp": datetime.now().isoformat(),
                "sessionstart": self.session_start.isoformat(),  # Backend uses 'sessionstart'
                "lastactivity": self.last_activity_time.isoformat(),  # Backend uses 'lastactivity'
                "totalseconds": round(self.total_seconds, 2),
                "activeseconds": round(self.active_seconds, 2),
                "idleseconds": round(self.idle_seconds, 2),
                "lockedseconds": round(self.locked_seconds, 2),
                "idlefor": round(self.idle_for, 2),
                "isidle": self.is_idle,
                "locked": self.is_locked,
                "mouseactive": False,
                "keyboardactive": False,
                "currentwindow": self.current_window,
                "currentprocess": self.current_process,
                "windowsopened": self.windows_opened[:],
                "browserhistory": [],
            }
            # decide inclusion under lock
            should_include = include_screenshot if include_screenshot is not None else bool(self.latest_screenshot_b64)
            if should_include and self.latest_screenshot_b64:
                payload["screenshot"] = self.latest_screenshot_b64
            return payload
    
    def reset_for_upload(self):
        with self.lock:
            self.latest_screenshot_b64 = None
    
    def reset_session(self):
        with self.lock:
            self.total_seconds = 0.0
            self.active_seconds = 0.0
            self.idle_seconds = 0.0
            self.locked_seconds = 0.0
            self.session_start = datetime.now()
            self.windows_opened = []

STATE = GlobalState()
CONFIG['device_id'] = STATE.device_id

# ============================================================================
# UTILITIES
# ============================================================================

def get_idle_time():
    try:
        last_input = win32api.GetLastInputInfo()
        current_tick = win32api.GetTickCount()
        return (current_tick - last_input) / 1000.0
    except:
        return 0

def is_screen_locked():
    try:
        return win32gui.GetForegroundWindow() == 0
    except:
        return True

def get_active_window_info():
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd == 0:
            return "Desktop", "explorer.exe"
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        return title, process.name()
    except:
        return "Unknown", "unknown.exe"

def capture_screenshot():
    try:
        img = ImageGrab.grab()
        if img.width > 1280:
            ratio = 1280 / img.width
            img = img.resize((1280, int(img.height * ratio)), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        # also save a local copy for debugging/inspection
        try:
            screens_dir = os.path.join(CONFIG['config_dir'], 'screenshots')
            os.makedirs(screens_dir, exist_ok=True)
            filename = datetime.now().strftime('%Y%m%d_%H%M%S') + '.jpg'
            filepath = os.path.join(screens_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(buf.getvalue())
            logger.info(f"[SCREENSHOT] Saved local copy: {filepath}")
        except Exception:
            logger.exception("[SCREENSHOT] Failed to save local copy")
        return base64.b64encode(buf.getvalue()).decode()
    except:
        return None

def check_mouse_movement():
    try:
        pos = win32api.GetCursorPos()
        if STATE.last_mouse_pos is None:
            STATE.last_mouse_pos = pos
            return False
        moved = pos != STATE.last_mouse_pos
        STATE.last_mouse_pos = pos
        return moved
    except:
        return False

# ============================================================================
# API CALLS - SYNCED WITH BACKEND tracker_routes.py
# ============================================================================

def verify_member(email):
    """
    Verify member email with backend
    Synced with: /tracker/verify-member endpoint in tracker_routes.py
    
    Backend flow:
    1. Validates tracker token (X-Tracker-Token header)
    2. Extracts company_id from token
    3. Queries members table: SELECT * FROM members WHERE company_id=X AND email=Y
    4. Registers device in devices table
    5. Returns member info
    """
    try:
        logger.info(f"[VERIFY] Email: {email}")
        
        if not CONFIG.get('tracker_token'):
            logger.error("[VERIFY] No tracker token configured")
            return False, None, "Token not configured. Please download tracker from admin dashboard."
        
        url = f"{CONFIG['backend_url']}/tracker/verify-member"
        
        # Backend expects these exact field names (see tracker_routes.py line ~180)
        payload = {
            "email": email.lower().strip(),
            "deviceid": STATE.device_id,      # Backend: data.get('deviceid')
            "hostname": STATE.hostname,       # Backend: data.get('hostname')
            "osinfo": STATE.os_info           # Backend: data.get('osinfo')
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-Tracker-Token': CONFIG['tracker_token']  # Backend validates this
        }
        
        logger.info(f"[VERIFY] Sending to: {url}")
        logger.info(f"[VERIFY] Device ID: {STATE.device_id}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        logger.info(f"[VERIFY] Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"[VERIFY] Response data: {data}")
            
            if data.get('success'):
                CONFIG['member_email'] = email.lower().strip()
                member = data.get('member', {})
                logger.info(f"[VERIFY] ✅ Verified: {member.get('name', 'Unknown')}")
                logger.info(f"[VERIFY] ✅ Member ID: {member.get('id')}")
                logger.info(f"[VERIFY] ✅ Device registered in DB")
                return True, member, "Verification successful"
            else:
                error = data.get('error', 'Verification failed')
                logger.error(f"[VERIFY] ❌ {error}")
                return False, None, error
        else:
            try:
                error_data = response.json()
                error = error_data.get('error', 'Server error')
                logger.error(f"[VERIFY] ❌ HTTP {response.status_code}: {error}")
                return False, None, error
            except:
                logger.error(f"[VERIFY] ❌ HTTP {response.status_code}")
                return False, None, f"Server error: {response.status_code}"
                
    except requests.exceptions.Timeout:
        logger.error("[VERIFY] ❌ Timeout")
        return False, None, "Backend timeout. Please check internet connection."
    except requests.exceptions.ConnectionError:
        logger.error("[VERIFY] ❌ Connection failed")
        return False, None, "Cannot connect to backend. Check internet."
    except Exception as e:
        logger.error(f"[VERIFY] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, None, str(e)

def punch_in():
    """
    Record punch in
    Synced with: /tracker/punch-in endpoint in tracker_routes.py
    
    Backend flow:
    1. Validates tracker token
    2. Gets member by email + company_id
    3. Gets device by deviceid
    4. Inserts into punchlogs table
    5. Updates member status to 'active'
    """
    try:
        if not CONFIG.get('member_email') or not CONFIG.get('tracker_token'):
            return False, "Not configured"
        
        logger.info(f"[PUNCH-IN] Email: {CONFIG['member_email']}")
        
        url = f"{CONFIG['backend_url']}/tracker/punch-in"
        
        # Backend expects these exact fields (see tracker_routes.py line ~280)
        payload = {
            "email": CONFIG['member_email'],
            "deviceid": STATE.device_id  # Backend: data.get('deviceid')
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-Tracker-Token': CONFIG['tracker_token']
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        logger.info(f"[PUNCH-IN] Response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"[PUNCH-IN] ✅ {data.get('message')}")
            logger.info(f"[PUNCH-IN] ✅ Punch log ID: {data.get('punchlogid')}")
            return True, data.get('message', 'Punched in successfully')
        else:
            try:
                error = response.json().get('error', 'Punch in failed')
                logger.error(f"[PUNCH-IN] ❌ {error}")
                return False, error
            except:
                return False, f"HTTP {response.status_code}"
                
    except Exception as e:
        logger.error(f"[PUNCH-IN] ❌ {e}")
        return False, str(e)

def punch_out():
    """
    Record punch out
    Synced with: /tracker/punch-out endpoint in tracker_routes.py
    
    Backend flow:
    1. Validates tracker token
    2. Gets member by email + company_id
    3. Finds active punch log
    4. Updates punch log with punch_out_time and duration
    5. Updates member status to 'offline'
    """
    try:
        if not CONFIG.get('member_email') or not CONFIG.get('tracker_token'):
            return False, "Not configured"
        
        logger.info(f"[PUNCH-OUT] Email: {CONFIG['member_email']}")
        
        url = f"{CONFIG['backend_url']}/tracker/punch-out"
        
        # Backend expects these exact fields (see tracker_routes.py line ~340)
        payload = {
            "email": CONFIG['member_email'],
            "deviceid": STATE.device_id
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-Tracker-Token': CONFIG['tracker_token']
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        logger.info(f"[PUNCH-OUT] Response: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"[PUNCH-OUT] ✅ {data.get('message')}")
            logger.info(f"[PUNCH-OUT] ✅ Duration: {data.get('workdurationseconds', 0)}s")
            return True, data.get('message', 'Punched out successfully')
        else:
            try:
                error = response.json().get('error', 'Punch out failed')
                logger.error(f"[PUNCH-OUT] ❌ {error}")
                return False, error
            except:
                return False, f"HTTP {response.status_code}"
                
    except Exception as e:
        logger.error(f"[PUNCH-OUT] ❌ {e}")
        return False, str(e)

def upload_data():
    """
    Upload tracking data
    Synced with: /tracker/upload endpoint in tracker_routes.py
    
    Backend flow:
    1. Validates tracker token
    2. Gets member and device
    3. Inserts into rawtrackerdata table
    4. Processes and inserts screenshot
    5. Processes activity logs
    6. Updates member and device status
    """
    try:
        if not CONFIG.get('member_email') or not CONFIG.get('tracker_token'):
            return False
        
        # let GlobalState.choose whether to include screenshot under lock
        payload = STATE.get_payload()
        
        url = f"{CONFIG['backend_url']}/tracker/upload"
        headers = {
            'Content-Type': 'application/json',
            'X-Tracker-Token': CONFIG['tracker_token']
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            logger.info("[UPLOAD] ✅ Data uploaded")
            STATE.reset_for_upload()
            return True
        else:
            logger.warning(f"[UPLOAD] ⚠️ Failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"[UPLOAD] ❌ {e}")
        return False

def heartbeat():
    """Send heartbeat to backend + check for configuration updates"""
    try:
        if not CONFIG.get('member_email') or not CONFIG.get('tracker_token'):
            return
        
        url = f"{CONFIG['backend_url']}/tracker/heartbeat"
        
        # NOTE: backend expects 'deviceid' (no underscore) similar to other endpoints
        payload = {
            'deviceid': STATE.device_id,
            'email': CONFIG['member_email'],
            'hostname': STATE.hostname,
            'os_info': STATE.os_info
        }
        
        response = requests.post(
            url,
            json=payload,
            headers={'X-Tracker-Token': CONFIG['tracker_token']},
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"[HEARTBEAT] ❤️ Sent successfully")
            
            # Check if it's time to sync configuration
            if config_manager.should_sync():
                logger.info("[HEARTBEAT] Configuration sync due, fetching...")
                config_manager.fetch_configuration()
        else:
            logger.warning(f"[HEARTBEAT] Failed: HTTP {response.status_code}")
            
    except Exception as e:
        logger.error(f"[HEARTBEAT] Error: {e}")

def fetch_configuration():
    """Fetch configuration from backend"""
    return config_manager.fetch_configuration()

# ============================================================================
# TRACKING THREADS
# ============================================================================

class ActivityTracker(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.last_check = time.time()
    
    def run(self):
        while self.running:
            if not STATE.is_tracking:
                time.sleep(CONFIG['activity_check_interval'])
                continue
            
            current = time.time()
            elapsed = current - self.last_check
            self.last_check = current
            
            idle_time = get_idle_time()
            locked = is_screen_locked()
            idle = idle_time >= CONFIG['idle_threshold']
            
            STATE.is_idle = idle
            STATE.is_locked = locked
            STATE.idle_for = idle_time
            
            if not locked:
                window, process = get_active_window_info()
                STATE.update_activity(window, process)
                if not idle:
                    STATE.last_activity_time = datetime.now()
            
            check_mouse_movement()
            
            active = not idle and not locked
            STATE.add_time(elapsed, active, idle, locked)
            
            time.sleep(CONFIG['activity_check_interval'])

class DataUploader(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
    
    def run(self):
        # give the other threads a moment to start and capture an initial
        # screenshot so the first upload has a chance to include it
        time.sleep(min(5, CONFIG['upload_interval']))
        while self.running:
            if STATE.is_tracking:
                payload = STATE.get_payload()  # let method decide screenshot atomically
                if 'screenshot' in payload:
                    logger.info("[UPLOAD] 📸 including screenshot in payload")
                else:
                    logger.info("[UPLOAD] (no screenshot)")
                upload_data()
            time.sleep(CONFIG['upload_interval'])

class HeartbeatSender(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
    
    def run(self):
        while self.running:
            if STATE.is_tracking:
                heartbeat()
            time.sleep(CONFIG['heartbeat_interval'])

class ConfigurationFetcher(Thread):
    """Periodically fetch configuration from backend to update intervals"""
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
    
    def run(self):
        logger.info("[CONFIG-THREAD] Configuration fetcher started")
        
        # Initial fetch after 5 seconds (give time for tracking to start)
        time.sleep(5)
        if STATE.is_tracking:
            logger.info("[CONFIG-THREAD] Performing initial configuration fetch")
            config_manager.fetch_configuration()
        
        # Then check every minute if sync is needed (checks should_sync internally)
        while self.running:
            time.sleep(60)  # Check every minute
            
            if STATE.is_tracking and config_manager.should_sync():
                logger.info("[CONFIG-THREAD] Configuration sync cycle triggered")
                config_manager.fetch_configuration()

class ScreenshotCapture(Thread):
    """Capture screenshots at intervals defined in configuration"""
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
    
    def run(self):
        logger.info("[SCREENSHOT-THREAD] Screenshot capture thread started")
        
        while self.running:
            if not STATE.is_tracking:
                time.sleep(5)
                continue
            
            try:
                # Capture screenshot
                screenshot_b64 = capture_screenshot()
                if screenshot_b64:
                    STATE.latest_screenshot_b64 = screenshot_b64
                    STATE.last_screenshot_time = datetime.now()
                    interval_min = CONFIG['screenshot_interval'] // 60
                    logger.info(f"[SCREENSHOT] 📸 Captured at {datetime.now().strftime('%H:%M:%S')} (interval: {interval_min}min)")
            except Exception as e:
                logger.error(f"[SCREENSHOT] ❌ Error: {e}")
            
            # Wait for the configured interval (dynamically updated from config)
            # Check every 30 seconds if interval changed, but only capture at full interval
            interval = CONFIG['screenshot_interval']
            elapsed = 0
            
            while elapsed < interval and self.running and STATE.is_tracking:
                sleep_time = min(30, interval - elapsed)
                time.sleep(sleep_time)
                elapsed += sleep_time
                
                # Check if config changed during wait
                if elapsed < interval and CONFIG['screenshot_interval'] != interval:
                    logger.info(f"[SCREENSHOT] ⚙️ Interval changed during wait, adjusting...")
                    break

# ============================================================================
# MODERN UI
# ============================================================================

class MinimalUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Work Eye Tracker")
        self.root.geometry("420x500")
        self.root.resizable(False, False)
        
        # Modern color scheme
        self.bg_primary = '#0f172a'      # Dark blue-black
        self.bg_secondary = '#1e293b'    # Dark slate
        self.accent_success = '#10b981'  # Green
        self.accent_danger = '#ef4444'   # Red
        self.accent_warning = '#f59e0b'  # Amber
        self.text_primary = '#ffffff'    # White
        self.text_secondary = '#cbd5e1'  # Light gray
        
        self.root.configure(bg=self.bg_primary)
        
        # Prevent window resizing
        self.root.resizable(False, False)
        
        # Set minimum window size
        self.root.minsize(420, 500)
        
        self.email_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.time_var = tk.StringVar(value="00:00:00")
        
        self.activity_thread = None
        self.upload_thread = None
        self.heartbeat_thread = None
        self.config_thread = None
        self.screenshot_thread = None
        
        self.tracking_start_time = None
        self.update_timer = None
        
        self.setup_ui()
        self.load_saved_email()
    
    def setup_ui(self):
        # === HEADER ===
        header_frame = tk.Frame(self.root, bg=self.bg_secondary, height=70)
        header_frame.pack(fill=tk.X, pady=(0, 0))
        header_frame.pack_propagate(False)
        
        # Logo/Title - centered
        title = tk.Label(
            header_frame,
            text="Work Eye",
            font=('Segoe UI', 18, 'bold'),
            bg=self.bg_secondary,
            fg=self.text_primary
        )
        title.pack(pady=(10, 0), expand=True)
        
        # Subtitle - centered
        subtitle = tk.Label(
            header_frame,
            text="Employee Monitoring System",
            font=('Segoe UI', 8),
            bg=self.bg_secondary,
            fg=self.text_secondary
        )
        subtitle.pack(pady=(0, 5), expand=True)
        
        # === MAIN CONTENT ===
        self.content_frame = tk.Frame(self.root, bg=self.bg_primary)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # === PUNCH IN VIEW ===
        self.punch_in_frame = tk.Frame(self.content_frame, bg=self.bg_primary)
        self.punch_in_frame.pack(fill=tk.BOTH, expand=True)
        
        # Email input section with better styling
        form_frame = tk.Frame(self.punch_in_frame, bg=self.bg_primary)
        form_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
        
        # Welcome message
        welcome_label = tk.Label(
            form_frame,
            text="Welcome Back!",
            font=('Segoe UI', 15, 'bold'),
            bg=self.bg_primary,
            fg=self.text_primary
        )
        welcome_label.pack(pady=(0, 4))
        
        instruction_label = tk.Label(
            form_frame,
            text="Enter your email to start tracking",
            font=('Segoe UI', 9),
            bg=self.bg_primary,
            fg=self.text_secondary
        )
        instruction_label.pack(pady=(0, 12))
        
        # Email label
        email_label = tk.Label(
            form_frame,
            text="📧 Email Address",
            font=('Segoe UI', 10, 'bold'),
            bg=self.bg_primary,
            fg=self.text_primary
        )
        email_label.pack(anchor='w', pady=(0, 5))
        
        # Email entry with custom styling
        email_frame = tk.Frame(form_frame, bg=self.bg_secondary, highlightthickness=2, highlightbackground=self.accent_success)
        email_frame.pack(fill=tk.X, pady=(0, 18))
        
        self.email_entry = tk.Entry(
            email_frame,
            textvariable=self.email_var,
            font=('Segoe UI', 11),
            relief='flat',
            bd=0,
            bg=self.bg_secondary,
            fg=self.text_primary,
            insertbackground=self.text_primary
        )
        self.email_entry.pack(fill=tk.X, padx=12, pady=10)
        self.email_entry.focus()
        
        # Bind focus events for better UX
        self.email_entry.bind('<FocusIn>', lambda e: email_frame.config(highlightbackground=self.accent_success))
        self.email_entry.bind('<FocusOut>', lambda e: email_frame.config(highlightbackground=self.accent_success))
        
        # PUNCH IN button
        self.punch_in_btn = tk.Button(
            form_frame,
            text="▶  PUNCH IN",
            font=('Segoe UI', 11, 'bold'),
            bg=self.accent_success,
            fg=self.text_primary,
            relief='flat',
            bd=0,
            height=2,
            command=self.handle_punch_in,
            cursor='hand2',
            activebackground='#059669',
            activeforeground=self.text_primary
        )
        self.punch_in_btn.pack(fill=tk.X, pady=(0, 10))
        
        # Info box
        info_frame = tk.Frame(form_frame, bg=self.bg_secondary, relief='flat')
        info_frame.pack(fill=tk.X, pady=(10, 0))
        
        info_text = tk.Label(
            info_frame,
            text="ℹ️  Your work activity will be tracked.",
            font=('Segoe UI', 8),
            bg=self.bg_secondary,
            fg=self.text_secondary,
            wraplength=340,
            justify=tk.LEFT
        )
        info_text.pack(padx=12, pady=10)
        
        # === PUNCH OUT VIEW ===
        self.punch_out_frame = tk.Frame(self.content_frame, bg=self.bg_primary)
        
        # Tracking info card
        tracking_card = tk.Frame(self.punch_out_frame, bg=self.bg_secondary, relief='flat')
        tracking_card.pack(fill=tk.X, padx=25, pady=(20, 15))
        
        status_title = tk.Label(
            tracking_card,
            text="Tracking Status",
            font=('Segoe UI', 11, 'bold'),
            bg=self.bg_secondary,
            fg=self.text_primary
        )
        status_title.pack(anchor='w', padx=15, pady=(12, 3))
        
        self.tracking_label = tk.Label(
            tracking_card,
            text="",
            font=('Segoe UI', 12, 'bold'),
            bg=self.bg_secondary,
            fg=self.accent_success
        )
        self.tracking_label.pack(anchor='w', padx=15, pady=(0, 10))
        
        # Time display
        time_frame = tk.Frame(tracking_card, bg=self.bg_secondary)
        time_frame.pack(fill=tk.X, padx=15, pady=(0, 12))
        
        time_label = tk.Label(
            time_frame,
            text="⏱️ Session Duration:",
            font=('Segoe UI', 9),
            bg=self.bg_secondary,
            fg=self.text_secondary
        )
        time_label.pack(anchor='w', pady=(0, 3))
        
        self.time_display = tk.Label(
            time_frame,
            textvariable=self.time_var,
            font=('Segoe UI', 24, 'bold'),
            bg=self.bg_secondary,
            fg=self.accent_success
        )
        self.time_display.pack(anchor='w', pady=(0, 8))
        
        # Stats
        stats_frame = tk.Frame(tracking_card, bg=self.bg_secondary)
        stats_frame.pack(fill=tk.X, padx=15, pady=(0, 12))
        
        status_text = tk.Label(
            stats_frame,
            text="🎥 Screenshots: Capturing  •  📊 Activity: Logging",
            font=('Segoe UI', 9),
            bg=self.bg_secondary,
            fg=self.text_secondary
        )
        status_text.pack(anchor='w')
        
        # PUNCH OUT button (large and prominent)
        button_frame = tk.Frame(self.punch_out_frame, bg=self.bg_primary)
        # don't expand the frame, let the button size itself
        button_frame.pack(pady=20)  # small vertical spacing only
        
        self.punch_out_btn = tk.Button(
            button_frame,
            text="⏹  PUNCH OUT",
            font=('Segoe UI', 10, 'bold'),  # smaller font
            bg=self.accent_danger,
            fg=self.text_primary,
            relief='flat',
            bd=0,
            height=1,  # minimal height
            padx=10,
            pady=5,
            command=self.handle_punch_out,
            cursor='hand2',
            activebackground='#dc2626',
            activeforeground=self.text_primary
        )
        # pack without fill/expand so button is only as big as its content
        self.punch_out_btn.pack(pady=5)
        
        # Bind enter key
        self.root.bind('<Return>', lambda e: self.handle_punch_in() if not STATE.is_tracking else None)
    
    def load_saved_email(self):
        try:
            if os.path.exists(CONFIG['config_file']):
                with open(CONFIG['config_file'], 'r') as f:
                    data = json.load(f)
                    if data.get('member_email'):
                        self.email_var.set(data['member_email'])
        except:
            pass
    
    def save_email(self):
        try:
            data = {
                'member_email': CONFIG.get('member_email'),
                'device_id': STATE.device_id,
            }
            with open(CONFIG['config_file'], 'w') as f:
                json.dump(data, f)
        except:
            pass
    
    def update_time_display(self):
        """Update the session duration timer"""
        if STATE.is_tracking and self.tracking_start_time:
            elapsed = time.time() - self.tracking_start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            self.time_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.update_timer = self.root.after(1000, self.update_time_display)
    
    def show_punch_in_view(self):
        self.punch_out_frame.pack_forget()
        self.punch_in_frame.pack(fill=tk.BOTH, expand=True)
        self.root.title("Work Eye - Punch In")
        if self.update_timer:
            self.root.after_cancel(self.update_timer)
            self.update_timer = None
    
    def show_punch_out_view(self):
        self.punch_in_frame.pack_forget()
        self.punch_out_frame.pack(fill=tk.BOTH, expand=True)
        
        email = CONFIG.get('member_email', 'User')
        self.root.title(f"Work Eye - Tracking: {email}")
        self.tracking_label.config(text=f"👤 {email}")
        
        # Start time display updates
        self.tracking_start_time = time.time()
        self.time_var.set("00:00:00")
        self.update_time_display()
    
    def handle_punch_in(self):
        email = self.email_var.get().strip()
        if not email:
            messagebox.showwarning("Warning", "Please enter your email")
            return
        
        try:
            self.punch_in_btn.config(state='disabled', text='⏳ Verifying...')
            self.root.update()
            
            # Verify member
            logger.info(f"[UI] Verifying member: {email}")
            result = verify_member(email)
            
            if result:
                logger.info("[UI] Member verified successfully")
                
                # Fetch initial configuration before starting tracking
                self.punch_in_btn.config(text='⚙️  Loading config...')
                self.root.update()
                
                logger.info("[STARTUP] Fetching initial configuration from server...")
                if config_manager.fetch_configuration():
                    logger.info("[STARTUP] ✅ Configuration loaded successfully")
                else:
                    logger.warning("[STARTUP] ⚠️ Using default configuration")
                
                # Punch in
                self.punch_in_btn.config(text='⏹  Punching in...')
                self.root.update()
                
                if punch_in():
                    STATE.is_tracking = True
                    
                    # Start all monitoring threads
                    logger.info("[UI] Starting monitoring threads...")
                    
                    self.activity_thread = ActivityTracker()
                    self.upload_thread = DataUploader()
                    self.heartbeat_thread = HeartbeatSender()
                    self.config_thread = ConfigurationFetcher()
                    self.screenshot_thread = ScreenshotCapture()
                    
                    self.activity_thread.start()
                    self.upload_thread.start()
                    self.heartbeat_thread.start()
                    self.config_thread.start()
                    self.screenshot_thread.start()
                    
                    self.save_email()
                    self.show_punch_out_view()
                    
                    logger.info("=" * 70)
                    logger.info("✅ TRACKING STARTED")
                    logger.info(f"👤 User: {email}")
                    logger.info(f"💻 Device: {STATE.device_id}")
                    logger.info(f"📸 Screenshot interval: {CONFIG['screenshot_interval']}s ({CONFIG['screenshot_interval']//60}min)")
                    logger.info(f"⏰ Idle threshold: {CONFIG['idle_threshold']}s ({CONFIG['idle_threshold']//60}min)")
                    logger.info(f"🔄 Config sync: Every 5 minutes")
                    logger.info("=" * 70)
                else:
                    messagebox.showerror("Error", "Failed to punch in. Please try again.")
                    self.punch_in_btn.config(state='normal', text='▶  PUNCH IN')
            else:
                messagebox.showerror("Error", "Email verification failed")
                self.punch_in_btn.config(state='normal', text='▶  PUNCH IN')
                
        except Exception as e:
            logger.error(f"[UI] Punch-in error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed: {str(e)}")
            self.punch_in_btn.config(state='normal', text='▶  PUNCH IN')
    
    def handle_punch_out(self):
        response = messagebox.askyesno(
            "Confirm Punch Out",
            "Stop tracking and punch out?"
        )
        if not response:
            return
        
        STATE.is_tracking = False
        if self.activity_thread:
            self.activity_thread.running = False
        if self.upload_thread:
            self.upload_thread.running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.running = False
        
        success, msg = punch_out()
        
        if success:
            messagebox.showinfo("✅ Punched Out", msg)
        else:
            messagebox.showwarning("⚠️  Punched Out", f"Tracking stopped.\n{msg}")
        
        STATE.reset_session()
        
        self.email_entry.config(state='normal')
        self.punch_in_btn.config(state='normal', text="▶  PUNCH IN")
        self.show_punch_in_view()
        
        logger.info("🛑 Tracking stopped")
    
    def start_tracking(self):
        STATE.is_tracking = True
        STATE.punch_in_time = datetime.now()
        STATE.session_start = datetime.now()
        
        # Fetch configuration before starting threads
        fetch_configuration()
        
        self.activity_thread = ActivityTracker()
        self.upload_thread = DataUploader()
        self.heartbeat_thread = HeartbeatSender()
        self.config_thread = ConfigurationFetcher()
        self.screenshot_thread = ScreenshotCapture()
        
        self.activity_thread.start()
        self.upload_thread.start()
        self.heartbeat_thread.start()
        self.config_thread.start()
        self.screenshot_thread.start()
        
        logger.info(f"✅ Tracking: {CONFIG['member_email']} (Device: {STATE.device_id})")
        logger.info(f"✅ Screenshot interval: {CONFIG['screenshot_interval']}s")
        logger.info(f"✅ Idle threshold: {CONFIG['idle_threshold']}s")
    
    def on_closing(self):
        if STATE.is_tracking:
            response = messagebox.askyesno(
                "Confirm Exit",
                "Tracking is active. Exit will punch you out.\n\nContinue?"
            )
            if not response:
                return
            
            STATE.is_tracking = False
            punch_out()
        
        if self.update_timer:
            self.root.after_cancel(self.update_timer)
        
        self.root.destroy()
    
    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    logger.info("="*70)
    logger.info("WORK TRACKER - Synced with Backend DB")
    logger.info("="*70)
    logger.info(f"Device ID: {STATE.device_id} (Auto-generated)")
    logger.info(f"Hostname: {STATE.hostname}")
    logger.info(f"Backend: {CONFIG['backend_url']}")
    logger.info("="*70)
    
    try:
        ui = MinimalUI()
        ui.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
