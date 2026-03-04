"""
APP.PY - Secure Multi-Tenant Flask Application with SPA Support
================================================================
[OK] Complete separation of admin and tracker auth
[OK] Strict company_id isolation
[OK] No auto-registration
[OK] SPA fallback for client-side routing
[OK] FIXED: API routes take priority over SPA fallback
[OK] Configuration management routes added
"""

import os
import sys
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from flask_socketio import SocketIO, join_room, emit
from dotenv import load_dotenv
from attendance_routes import attendance_bp

# Ensure console uses utf-8 so unicode prints don't crash on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


load_dotenv()

# ======================================================================
# FLASK APP SETUP
# ======================================================================

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-in-prod")

CORS(
    app,
    resources={
        r"/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": [
                "Content-Type",
                "Authorization",
                "X-Tracker-Token",
                "x-api-key"
            ]
        }
    }
)

# ======================================================================
# SOCKET.IO SETUP
# ======================================================================

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    ping_timeout=20,
    ping_interval=10
)

# ======================================================================
# DATABASE INIT
# ======================================================================

from db import check_db_health

print("[SYSTEM] Multi-Tenant Secure Backend Starting...")

# ======================================================================
# BLUEPRINTS - ALL ROUTES (REGISTER BEFORE SPA FALLBACK!)
# ======================================================================

def load_blueprint(blueprint, name):
    try:
        app.register_blueprint(blueprint)
        print(f"[OK] {name} routes loaded")
    except Exception as e:
        print(f"[WARN] {name} routes failed: {e}")

# Admin routes (dashboard authentication + management)
from admin_auth_routes import admin_auth_bp
from members_routes import members_bp
from dashboard_routes import dashboard_bp
from analytics_routes import analytics_bp

# NEW: Screenshots, Activity, Tracker Download, Configuration
from screenshots_routes import screenshots_bp
from activity_routes import activity_bp
from configuration_routes import configuration_bp  # NEW!

# Tracker routes (token-based, member email verification)
from tracker_routes import tracker_bp

load_blueprint(admin_auth_bp, "Admin Auth")
load_blueprint(members_bp, "Members Management")
load_blueprint(dashboard_bp, "Dashboard")
load_blueprint(analytics_bp, "Analytics")
load_blueprint(screenshots_bp, "Screenshots")
load_blueprint(activity_bp, "Activity")
load_blueprint(configuration_bp, "Configuration")  # NEW!
load_blueprint(tracker_bp, "Tracker")
load_blueprint(attendance_bp, "Attendance")


# ======================================================================
# HEALTH CHECK
# ======================================================================

@app.route("/health")
def health():
    healthy = check_db_health()
    
    return jsonify({
        "status": "healthy" if healthy else "degraded",
        "database": "connected" if healthy else "disconnected",
        "service": "work-eye-secure-backend",
        "architecture": "multi-tenant-isolated"
    }), 200 if healthy else 503

@app.route("/api")
def api_root():
    """API root - returns API information"""
    return jsonify({
        "service": "Work-Eye Secure Backend",
        "version": "4.3",  # Incremented version
        "status": "online",
        "architecture": "multi-tenant",
        "admin_endpoints": [
            "POST /auth/admin/signup",
            "POST /auth/admin/login",
            "GET /auth/admin/validate-token",
            "POST /admin/members",
            "GET /admin/members",
            "GET /api/dashboard/stats",
            "GET /api/dashboard/member/<id>/live",
            "GET /api/tracker/download",
            "GET /api/screenshots/<member_id>",
            "GET /api/screenshots/image/<screenshot_id>",
            "GET /api/activity-logs/<member_id>",
            "GET /api/website-visits/<member_id>",
            "GET /api/app-usage/<member_id>",
            "GET /api/configuration",
            "POST /api/configuration"
        ],
        "tracker_endpoints": [
            "POST /tracker/verify-member",
            "POST /tracker/punch-in",
            "POST /tracker/punch-out",
            "POST /tracker/upload",
            "POST /tracker/heartbeat",
            "GET /api/tracker/configuration"
        ]
    })

# ======================================================================
# SOCKET EVENTS (COMPANY SCOPED)
# ======================================================================

@socketio.on("connect")
def on_connect():
    print("🔌 Client connected")

@socketio.on("disconnect")
def on_disconnect():
    print("🔌 Client disconnected")

@socketio.on("join_company")
def on_join_company(data):
    company_id = data.get("company_id")
    if not company_id:
        return
    
    room = f"company_{company_id}"
    join_room(room)
    emit("joined", {"room": room})
    print(f"📡 Joined room {room}")

# ======================================================================
# ERROR HANDLERS - CRITICAL FIX
# ======================================================================

@app.errorhandler(404)
def not_found(error):
    """
    Handle 404 errors
    
    CRITICAL FIX: Only return SPA for browser requests, not API calls
    This prevents API endpoints from returning index.html
    """
    # Check if this is an API request
    if request.path.startswith('/api/') or request.path.startswith('/tracker/') or request.path.startswith('/auth/') or request.path.startswith('/admin/'):
        # API request - return JSON error
        return jsonify({"error": "Endpoint not found"}), 404
    
    # Browser request for SPA route - return index.html
    if app.static_folder and os.path.exists(os.path.join(app.static_folder, 'index.html')):
        return send_from_directory(app.static_folder, 'index.html')
    
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def server_error(_):
    return jsonify({"error": "Server error"}), 500

# ======================================================================
# SPA FALLBACK ROUTING - MUST BE LAST!
# ======================================================================

@app.route("/")
def root():
    return jsonify({
        "status": "Backend online",
        "service": "Work-Eye API"
    }), 200


# ======================================================================
# MAIN
# ======================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
