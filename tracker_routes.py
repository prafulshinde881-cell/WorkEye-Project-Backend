 
# """
# TRACKER ROUTES - WITH COMPREHENSIVE DEBUGGING
# ==============================================
# Handles all tracker endpoints with detailed logging
# """

# from flask import Blueprint, request, jsonify, send_file, after_this_request, current_app
# from db import get_db
# from datetime import datetime, timedelta
# import base64
# import json
# from PIL import Image
# from io import BytesIO
# import os
# import tempfile
# from functools import wraps
# from datetime import datetime, timezone
# import pytz


# import cloudinary
# import cloudinary.uploader

# cloudinary.config(
#     cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
#     api_key=os.getenv("CLOUDINARY_API_KEY"),
#     api_secret=os.getenv("CLOUDINARY_API_SECRET")
# )

# print("CLOUDINARY_CLOUD_NAME:", os.getenv("CLOUDINARY_CLOUD_NAME"))
# print("CLOUDINARY_API_KEY:", os.getenv("CLOUDINARY_API_KEY"))
# print("CLOUDINARY_API_SECRET:", os.getenv("CLOUDINARY_API_SECRET"))
# # Filesystem save configuration (optional)
# # Read from environment: set SAVE_SCREENSHOTS_TO_FS=true and SCREENSHOT_SAVE_PATH to enable
# SAVE_SCREENSHOTS_TO_FS = os.getenv('SAVE_SCREENSHOTS_TO_FS', 'true').lower() in ('1','true','yes')
# SCREENSHOT_SAVE_PATH = os.getenv('SCREENSHOT_SAVE_PATH', os.path.join(os.getcwd(), 'screenshots'))
# # Only save to fs when member is punched in (configurable)
# SAVE_SCREENSHOTS_ONLY_WHEN_PUNCHED_IN = os.getenv('SAVE_SCREENSHOTS_ONLY_WHEN_PUNCHED_IN', 'true').lower() in ('1','true','yes')
# # Ensure base path exists when enabled
# if SAVE_SCREENSHOTS_TO_FS:
#     try:
#         os.makedirs(SCREENSHOT_SAVE_PATH, exist_ok=True)
#     except Exception as e:
#         print(f"⚠️ Could not create screenshot base directory '{SCREENSHOT_SAVE_PATH}': {e}")

# tracker_bp = Blueprint('tracker', __name__)


# def utc_now():
#     return datetime.now(timezone.utc)


# def ensure_utc(dt):
#     if dt is None:
#         return None
#     return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# def verify_tracker_token(token: str):
#     try:
#         decoded = base64.b64decode(token.encode()).decode()
#         return int(decoded.split(':', 1)[0])
#     except Exception:
#         return None

# def emit_member_status_update(company_id, member_id, status):
#     """Emit member status update via Socket.IO (best effort)"""
#     try:
#         # Use the Socket.IO server instance from the main app so we can emit
#         # from regular HTTP routes (works from any thread/process where app is imported).
#         from app import socketio

#         message = {
#             'member_id': member_id,
#             'status': status,
#             'timestamp': datetime.utcnow().isoformat()
#         }

#         room = f"company_{company_id}"
#         socketio.emit('member_status_update', message, room=room, namespace='/')
#         print(f"📡 ✅ Emitted member_status_update via Socket.IO: member_id={member_id}, status={status}")

#     except RuntimeError as e:
#         # emit() can only be called from socket handlers
#         print(f"⚠️ Cannot emit from HTTP route: {e}")
#         # Status is already updated in database, frontend will fetch it
#         print(f"⚠️ Status updated in database: member_id={member_id}, status={status}")
#     except Exception as e:
#         print(f"⚠️ Failed to emit status update: {e}")
#         # Status is still in database, frontend will see it on refresh


# def verify_tracker_token(token: str):
#     """Verify tracker token and extract company_id"""
#     try:
#         if not token or not isinstance(token, str):
#             # avoid unicode in logs to prevent encoding errors
#             print("Token is None or not string")
#             return None

#         decoded = base64.b64decode(token.encode()).decode()
#         parts = decoded.split(':', 1)

#         if len(parts) >= 1:
#             company_id = int(parts[0])
#             # log without emoji
#             print(f"Token decoded: company_id={company_id}")
#             return company_id

#         return None
#     except Exception as e:
#         print(f"Token verification error: {e}")
#         return None


# def require_tracker_token(f):
#     """Decorator: Require tracker token authentication"""
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         # Get token from header
#         tracker_token = request.headers.get('X-Tracker-Token')

#         if not tracker_token:
#             # Try to get from body
#             try:
#                 data = request.get_json(silent=True) or {}
#                 tracker_token = data.get('tracker_token')
#             except:
#                 pass

#         if not tracker_token:
#             print("❌ No tracker token provided in request")
#             return jsonify({"error": "Tracker token required"}), 401

#         # Verify token and get company_id
#         company_id = verify_tracker_token(tracker_token)

#         if not company_id:
#             print(f"❌ Invalid tracker token format")
#             return jsonify({"error": "Invalid tracker token"}), 401

#         try:
#             with get_db() as conn:
#                 cur = conn.cursor()

#                 # Check what columns exist in companies table
#                 cur.execute("""
#                     SELECT column_name FROM information_schema.columns 
#                     WHERE table_name = 'companies'
#                 """)
#                 company_cols = [row['column_name'] for row in cur.fetchall()]
#                 print(f"✅ Companies table columns: {company_cols}")

#                 # Build query based on available columns
#                 select_cols = ['id']

#                 # Detect name column
#                 if 'company_name' in company_cols:
#                     select_cols.append('company_name as name')
#                 elif 'name' in company_cols:
#                     select_cols.append('name')
#                 elif 'companyname' in company_cols:
#                     select_cols.append('companyname as name')

#                 # Add tracker_token if exists
#                 if 'tracker_token' in company_cols:
#                     select_cols.append('tracker_token')

#                 # FIXED: Detect is_active column properly
#                 if 'is_active' in company_cols:
#                     isactive_col = 'is_active'
#                 elif 'isactive' in company_cols:
#                     isactive_col = 'isactive'
#                 else:
#                     isactive_col = 'is_active'  # Default fallback

#                 # Build and execute query with detected column name
#                 query = f"SELECT {', '.join(select_cols)} FROM companies WHERE id = %s AND {isactive_col} = TRUE"
#                 print(f"🔍 Token verification query: {query}")

#                 cur.execute(query, (company_id,))
#                 company = cur.fetchone()

#                 if not company:
#                     print(f"❌ Company {company_id} not found or inactive")
#                     return jsonify({"error": "Invalid or inactive company"}), 401

#                 # Optionally verify tracker_token matches if column exists
#                 if 'tracker_token' in company_cols and company.get('tracker_token'):
#                     if company['tracker_token'] != tracker_token:
#                         print(f"❌ Tracker token mismatch for company {company_id}")
#                         return jsonify({"error": "Invalid tracker token"}), 401

#                 company_name = company.get('name', 'Unknown')
#                 print(f"✅ Token verified for company {company_id}: {company_name}")

#         except Exception as e:
#             print(f"❌ Database error during token verification: {e}")
#             import traceback
#             traceback.print_exc()
#             return jsonify({"error": "Authentication failed"}), 500

#         # Store company_id in request for use in endpoint
#         request.tracker_company_id = company_id
#         request.tracker_token = tracker_token

#         return f(*args, **kwargs)

#     return decorated_function



# # ============================================================================
# # TRACKER DOWNLOAD
# # ============================================================================

# @tracker_bp.route('/api/tracker/download', methods=['GET'])
# def download_tracker():
#     """Download tracker with embedded company token"""
#     try:
#         # Get JWT token from Authorization header
#         auth_header = request.headers.get('Authorization', '')

#         if not auth_header.startswith('Bearer '):
#             return jsonify({"error": "Authentication required. Please log in."}), 401

#         jwt_token = auth_header.replace('Bearer ', '').strip()

#         # Verify admin JWT
#         from admin_auth_routes import verify_admin_jwt

#         try:
#             payload = verify_admin_jwt(jwt_token)
#             admin_id = payload['admin_id']
#             company_id = payload['company_id']
#             admin_email = payload['email']
#         except Exception as e:
#             print(f"❌ JWT verification failed: {e}")
#             return jsonify({"error": f"Authentication failed: {str(e)}"}), 401

#         print(f"✅ Tracker download request from admin: {admin_email}, company: {company_id}")

#         with get_db() as conn:
#             cur = conn.cursor()

#             # Check companies table columns
#             cur.execute("""
#                 SELECT column_name FROM information_schema.columns 
#                 WHERE table_name = 'companies'
#             """)
#             company_cols = [row['column_name'] for row in cur.fetchall()]
#             print(f"📋 Companies table columns: {company_cols}")

#             # FIXED: Properly detect column names with underscores
#             # Check for company_name (with underscore), companyname (without), or name
#             if 'company_name' in company_cols:
#                 name_col = 'company_name'
#             elif 'companyname' in company_cols:
#                 name_col = 'companyname'
#             else:
#                 name_col = 'name'

#             print(f"✅ Using company name column: {name_col}")

#             # Build select query
#             select_cols = ['id', f'{name_col} as companyname']

#             if 'tracker_token' in company_cols:
#                 select_cols.append('tracker_token')
#                 has_tracker_token = True
#             else:
#                 has_tracker_token = False

#             # Determine isactive column name
#             if 'is_active' in company_cols:
#                 isactive_col = 'is_active'
#             elif 'isactive' in company_cols:
#                 isactive_col = 'isactive'
#             else:
#                 isactive_col = 'is_active'  # Default fallback

#             query = f"SELECT {', '.join(select_cols)} FROM companies WHERE id = %s AND {isactive_col} = TRUE"
#             print(f"🔍 Executing query: {query}")

#             cur.execute(query, (company_id,))
#             company = cur.fetchone()

#             if not company:
#                 return jsonify({"error": "Company not found or inactive"}), 404

#             company_name = company['companyname']

#             # Get or generate tracker token
#             if has_tracker_token and company.get('tracker_token'):
#                 tracker_token = company['tracker_token']
#                 print(f"✅ Using existing tracker_token for company {company_id}")
#             else:
#                 # Generate token
#                 import secrets
#                 token_data = f"{company_id}:{secrets.token_urlsafe(32)}"
#                 tracker_token = base64.b64encode(token_data.encode()).decode()
#                 print(f"✅ Generated new tracker_token for company {company_id}")

#                 # Try to save it if column exists
#                 if has_tracker_token:
#                     try:
#                         cur.execute("UPDATE companies SET tracker_token = %s WHERE id = %s", (tracker_token, company_id))
#                         conn.commit()
#                         print(f"✅ Saved tracker_token to database")
#                     except Exception as e:
#                         print(f"⚠️ Could not save tracker_token: {e}")

#             # FIXED: Try multiple possible locations for tracker file
#             backend_dir = os.path.dirname(os.path.abspath(__file__))

#             # List of possible paths to check
#             possible_paths = [
#                 os.path.join(backend_dir, 'wkv0.0.py'),  # Same directory as tracker_routes.py
#                 os.path.join(os.getcwd(), 'wkv0.0.py'),  # Current working directory
#                 os.path.join(backend_dir, '..', 'wkv0.0.py'),  # Parent directory
#                 '/opt/render/project/src/wkv0.0.py',  # Render deployment path
#                 'wkv0.0.py',  # Relative path
#             ]

#             tracker_file_path = None

#             print(f"🔍 Searching for wkv0.0.py...")
#             print(f"📂 Backend dir: {backend_dir}")
#             print(f"📂 Current working dir: {os.getcwd()}")

#             try:
#                 files_in_dir = os.listdir(backend_dir)
#                 print(f"📂 Files in backend dir ({len(files_in_dir)} total): {files_in_dir[:15]}")
#             except Exception as e:
#                 print(f"⚠️ Could not list backend dir: {e}")

#             for path in possible_paths:
#                 print(f"   Checking: {path}")
#                 if os.path.exists(path):
#                     tracker_file_path = path
#                     print(f"✅ Found tracker file at: {path}")
#                     break

#             if not tracker_file_path:
#                 print(f"❌ Tracker template not found in any location!")
#                 return jsonify({
#                     "error": "Tracker template file not found on server",
#                     "details": "wkv0.0.py file is missing. Please ensure it's uploaded to the backend repository.",
#                     "searched_paths": possible_paths
#                 }), 500

#             with open(tracker_file_path, 'r', encoding='utf-8') as f:
#                 tracker_content = f.read()

#             print(f"✅ Tracker file read successfully ({len(tracker_content)} bytes)")

#             # Inject token and company_id
#             replacements = {
#                 "'tracker_token': None": f"'tracker_token': '{tracker_token}'",
#                 '"tracker_token": None': f'"tracker_token": "{tracker_token}"',
#                 "'company_id': None": f"'company_id': {company_id}",
#                 '"company_id": None': f'"company_id": {company_id}',
#             }

#             for old_value, new_value in replacements.items():
#                 if old_value in tracker_content:
#                     tracker_content = tracker_content.replace(old_value, new_value)
#                     print(f"✅ Replaced: {old_value[:30]}...")

#             # Add header comment
#             header_comment = f'''"""
# ╔═══════════════════════════════════════════════════════════════╗
# ║                    WORK-EYE TRACKER                           ║
# ║              Pre-Configured for {company_name[:30].ljust(30)} ║
# ╠═══════════════════════════════════════════════════════════════╣
# ║  Company ID: {str(company_id).ljust(48)} ║
# ║  Token: ***{tracker_token[-8:].ljust(45)} ║
# ║  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC').ljust(45)} ║
# ╠═══════════════════════════════════════════════════════════════╣
# ║  INSTRUCTIONS:                                                ║
# ║  1. Run this file on employee computer                        ║
# ║  2. Employee enters their registered email                    ║
# ║  3. Tracker automatically verifies and starts                 ║
# ╚═══════════════════════════════════════════════════════════════╝
# """

# '''
#             tracker_content = header_comment + tracker_content

#             # Save to temp file
#             temp_fd, temp_file_path = tempfile.mkstemp(suffix='.py', prefix='workeye_tracker_')

#             with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_file:
#                 temp_file.write(tracker_content)

#             # Sanitize company name for filename
#             sanitized_company = ''.join(c for c in company_name if c.isalnum() or c in [' ', '-', '_']).strip()
#             sanitized_company = sanitized_company.replace(' ', '_')
#             output_filename = f"WorkEyeTracker_{sanitized_company}.py"

#             @after_this_request
#             def cleanup(response):
#                 try:
#                     if os.path.exists(temp_file_path):
#                         os.unlink(temp_file_path)
#                 except Exception as e:
#                     print(f"⚠️ Failed to cleanup temp file: {e}")
#                 return response

#             print(f"✅ Tracker generated successfully: {output_filename}")

#             return send_file(
#                 temp_file_path,
#                 mimetype='text/x-python',
#                 as_attachment=True,
#                 download_name=output_filename
#             )

#     except Exception as e:
#         print(f"❌ Tracker download error: {e}")
#         import traceback
#         traceback.print_exc()
#         return jsonify({"error": "Failed to generate tracker", "details": str(e)}), 500




# # ============================================================================
# # VERIFY MEMBER
# # ============================================================================

# @tracker_bp.route('/tracker/verify-member', methods=['POST'])
# @require_tracker_token
# def verify_member():
#     """Verify member email and register device"""
#     try:
#         data = request.get_json(silent=True) or {}
#         company_id = request.tracker_company_id

#         email = data.get('email', '').lower().strip()
#         deviceid = data.get('deviceid', '')

#         print("="*70)
#         print("🔍 VERIFY MEMBER START")
#         print("="*70)
#         print(f"📧 Email: '{email}'")
#         print(f"🏢 Company ID: {company_id}")
#         print(f"💻 Device ID: {deviceid}")

#         if not email:
#             print("❌ Email is required but not provided")
#             return jsonify({"error": "Email required"}), 400

#         if not deviceid:
#             print("❌ Device ID is required but not provided")
#             return jsonify({"error": "Device ID required"}), 400

#         with get_db() as conn:
#             cur = conn.cursor()

#             # Check members table columns
#             cur.execute("""
#                 SELECT column_name FROM information_schema.columns 
#                 WHERE table_name = 'members'
#             """)
#             member_cols = [row['column_name'] for row in cur.fetchall()]
#             print(f"✅ Members table columns: {member_cols}")

#             # Determine name column
#             if 'full_name' in member_cols:
#                 name_col = 'full_name'
#             elif 'name' in member_cols:
#                 name_col = 'name'
#             elif 'fullname' in member_cols:
#                 name_col = 'fullname'
#             else:
#                 print("❌ No name column found in members table!")
#                 return jsonify({"error": "Database configuration error"}), 500

#             # Determine company_id column
#             if 'company_id' in member_cols:
#                 company_col = 'company_id'
#             elif 'companyid' in member_cols:
#                 company_col = 'companyid'
#             else:
#                 company_col = 'company_id'

#             # Determine is_active column
#             if 'is_active' in member_cols:
#                 active_col = 'is_active'
#             elif 'isactive' in member_cols:
#                 active_col = 'isactive'
#             else:
#                 active_col = 'is_active'

#             print(f"✅ Using columns: name={name_col}, company={company_col}, active={active_col}")

#             # Query for member
#             query = f"""
#                 SELECT id, email, {name_col} as membername, position, {active_col} as isactive 
#                 FROM members 
#                 WHERE {company_col} = %s AND email = %s
#             """
#             print(f"🔍 Executing query: {query}")
#             print(f"🔍 Parameters: {company_col}={company_id}, email='{email}'")

#             cur.execute(query, (company_id, email))
#             member = cur.fetchone()

#             if not member:
#                 print("❌ Member NOT FOUND!")

#                 # Debug: Check total members for this company
#                 cur.execute(f"SELECT COUNT(*) as count FROM members WHERE {company_col} = %s", (company_id,))
#                 count = cur.fetchone()['count']
#                 print(f"📊 Total members for company {company_id}: {count}")

#                 # Debug: List all members for this company
#                 cur.execute(f"SELECT id, email, {name_col} as name FROM members WHERE {company_col} = %s LIMIT 5", (company_id,))
#                 all_members = cur.fetchall()
#                 print(f"📋 Existing members:")
#                 for m in all_members:
#                     print(f"   - ID: {m['id']}, Email: '{m['email']}', Name: {m['name']}")

#                 return jsonify({
#                     "error": f"Email '{email}' not found in company. Contact your admin.",
#                     "debug_info": f"Total members in company: {count}"
#                 }), 404

#             print("✅ Member FOUND!")
#             print(f"   - Member ID: {member['id']}")
#             print(f"   - Member Name: {member['membername']}")
#             print(f"   - Member Position: {member.get('position', 'N/A')}")
#             print(f"   - Member Active: {member.get('isactive', True)}")

#             # Check if member is active
#             if not member.get('isactive', True):
#                 print("❌ Member account is INACTIVE")
#                 return jsonify({"error": "Member account is inactive"}), 403

#             member_id = member['id']
#             member_name = member.get('membername', 'Unknown')

#             # Register/update device
#             print("💻 Checking devices table...")

#             # Check devices table columns
#             cur.execute("""
#                 SELECT column_name FROM information_schema.columns 
#                 WHERE table_name = 'devices'
#             """)
#             device_cols = [row['column_name'] for row in cur.fetchall()]
#             print(f"✅ Devices table columns: {device_cols}")

#             # Determine device column names
#             if 'company_id' in device_cols:
#                 dev_company_col = 'company_id'
#                 dev_member_col = 'member_id'
#                 dev_device_col = 'device_id'
#                 dev_name_col = 'device_name'
#             else:
#                 dev_company_col = 'companyid'
#                 dev_member_col = 'memberid'
#                 dev_device_col = 'deviceid'
#                 dev_name_col = 'devicename'

#             print(f"✅ Using device columns: {dev_company_col}, {dev_member_col}, {dev_device_col}")

#             cur.execute(f"""
#                 SELECT id, {dev_name_col} as devicename, status 
#                 FROM devices 
#                 WHERE {dev_company_col} = %s AND {dev_member_col} = %s AND {dev_device_col} = %s
#             """, (company_id, member_id, deviceid))

#             device = cur.fetchone()

#             if device:
#                 device_db_id = device['id']
#                 print(f"✅ Existing device found (DB ID: {device_db_id})")

#                 # Update device member_id if needed (device can be reassigned to new member)
#                 hostname = data.get('hostname', 'Unknown')
#                 osinfo = data.get('osinfo', 'Unknown OS')

#                 if 'os_info' in device_cols:
#                     osinfo_col = 'os_info'
#                 elif 'osinfo' in device_cols:
#                     osinfo_col = 'osinfo'
#                 else:
#                     osinfo_col = 'os_info'

#                 cur.execute(f"""
#                     UPDATE devices 
#                     SET {dev_member_col} = %s, 
#                         {dev_name_col} = %s, 
#                         hostname = %s, 
#                         {osinfo_col} = %s,
#                         last_seen_at = NOW(),
#                         status = 'active'
#                     WHERE id = %s
#                 """, (member_id, hostname, hostname, osinfo, device_db_id))
#                 print(f"✅ Device updated with current member and status")
#             else:
#                 # Register new device
#                 print("💻 Registering new device...")
#                 hostname = data.get('hostname', 'Unknown')
#                 osinfo = data.get('osinfo', 'Unknown OS')

#                 # FIXED: Detect os_info column name
#                 if 'os_info' in device_cols:
#                     osinfo_col = 'os_info'
#                 elif 'osinfo' in device_cols:
#                     osinfo_col = 'osinfo'
#                 else:
#                     osinfo_col = 'os_info'

#                 print(f"✅ Using osinfo column: {osinfo_col}")

#                 # Check if device exists for any member in this company (handle reassignment)
#                 cur.execute(f"""
#                     SELECT id, {dev_member_col} as current_member_id 
#                     FROM devices 
#                     WHERE {dev_company_col} = %s AND {dev_device_col} = %s
#                 """, (company_id, deviceid))

#                 existing_device = cur.fetchone()

#                 if existing_device:
#                     # Device exists but for different member - reassign it
#                     device_db_id = existing_device['id']
#                     print(f"💻 Device exists for another member, reassigning...")

#                     cur.execute(f"""
#                         UPDATE devices 
#                         SET {dev_member_col} = %s, 
#                             {dev_name_col} = %s, 
#                             hostname = %s, 
#                             {osinfo_col} = %s,
#                             last_seen_at = NOW(),
#                             status = 'active'
#                         WHERE id = %s
#                     """, (member_id, hostname, hostname, osinfo, device_db_id))
#                     print(f"✅ Device reassigned to current member (DB ID: {device_db_id})")
#                 else:
#                     # Truly new device - insert it
#                     cur.execute(f"""
#                         INSERT INTO devices ({dev_company_col}, {dev_member_col}, {dev_device_col}, {dev_name_col}, hostname, {osinfo_col}, status)
#                         VALUES (%s, %s, %s, %s, %s, %s, 'active')
#                         RETURNING id
#                     """, (company_id, member_id, deviceid, hostname, hostname, osinfo))

#                     result = cur.fetchone()
#                     device_db_id = result['id'] if result else None

#                     if device_db_id:
#                         print(f"✅ New device registered (DB ID: {device_db_id})")
#                     else:
#                         print("⚠️ Device registration returned no ID")


#             print("="*70)
#             print("✅ VERIFY SUCCESS!")
#             print(f"👤 Member: {member_name} ({email})")
#             print(f"💻 Device: {device_db_id}")
#             print("="*70)

#             return jsonify({
#                 "success": True,
#                 "message": "Member verified successfully",
#                 "member": {
#                     "id": member_id,
#                     "email": member['email'],
#                     "name": member_name,
#                     "fullname": member_name,
#                     "position": member.get('position', 'Member')
#                 },
#                 "device_id": device_db_id
#             }), 200

#     except Exception as e:
#         print(f"❌ VERIFY EXCEPTION: {e}")
#         import traceback
#         traceback.print_exc()
#         return jsonify({
#             "error": "Internal server error during verification",
#             "details": str(e)
#         }), 500





# # ==============================
# # PUNCH IN
# # ==============================

# @tracker_bp.route('/tracker/punch-in', methods=['POST'])
# @require_tracker_token
# def tracker_punch_in():
#     """Record punch in (session-based design)"""
#     try:
#         print("Updated punch in 2")
#         data = request.get_json(silent=True) or {}
#         company_id = request.tracker_company_id
#         email = data.get('email', '').lower().strip()
#         deviceid = data.get('deviceid', '')

#         if not email or not deviceid:
#             return jsonify({"error": "Email and deviceid required"}), 400

#         with get_db() as conn:
#             cur = conn.cursor()

#             # Get member
#             cur.execute("""
#                         SELECT id FROM members
#                         WHERE company_id = %s AND email = %s
#                         """, (company_id, email))
#             member = cur.fetchone()

#             if not member:
#                 return jsonify({"error": "Member not found"}), 404

#             member_id = member['id']

#             # Check existing open session
#             cur.execute("""
#                         SELECT id FROM punch_logs
#                         WHERE company_id = %s AND member_id = %s AND punch_out_time IS NULL
#                         ORDER BY punch_in_time DESC
#                             LIMIT 1
#                         """, (company_id, member_id))

#             existing = cur.fetchone()
#             if existing:
#                 return jsonify({
#                     "success": True,
#                     "message": "Already punched in",
#                     "punchlogid": existing['id']
#                 }), 200

#             now = utc_now()                           # aware UTC
#             ist = pytz.timezone("Asia/Kolkata")

#             now_ist = now.astimezone(ist)             # ✅ real conversion
#             now_db = now_ist.replace(tzinfo=None)     # optional: naive IST for DB


#             cur.execute("""
#                         SELECT id FROM devices
#                         WHERE company_id = %s AND member_id = %s AND device_id = %s
#                         """, (company_id, member_id, deviceid))

#             device = cur.fetchone()
#             device_db_id = int(device['id'])

#             print("device id type: ", type(device_db_id))
#             print("deviceid: ",device_db_id)

#             # Insert new session row
#             cur.execute("""
#                         INSERT INTO punch_logs (
#                             company_id, member_id, device_id,
#                             punch_in_time, punch_date, status
#                         )
#                         VALUES (%s, %s, %s, %s, %s, 'punched_in')
#                             RETURNING id
#                         """, (company_id, member_id, device_db_id, now, now_db.date()))

#             punchlog_id = cur.fetchone()['id']

#             # Update member state
#             cur.execute("""
#                         UPDATE members
#                         SET last_punch_in_at = %s, status = 'active', is_punched_in = TRUE
#                         WHERE id = %s
#                         """, (now_db, member_id))

#             conn.commit()

#             return jsonify({
#                 "success": True,
#                 "message": "Punched in successfully",
#                 "punchlogid": punchlog_id,
#                 "punchintime": now.isoformat()
#             }), 200

#     except Exception as e:
#         print("❌ PUNCH-IN ERROR:", e)
#         return jsonify({"error": "Failed to record punch in"}), 500



# # ============================================================================
# # PUNCH OUT
# # ============================================================================

# @tracker_bp.route('/tracker/punch-out', methods=['POST'])
# @require_tracker_token
# def tracker_punch_out():
#     """Record punch out (updates existing session row)"""
#     try:
#         print("Updated punch out 2")
#         data = request.get_json(silent=True) or {}
#         company_id = request.tracker_company_id

#         email = data.get('email', '').lower().strip()

#         if not email:
#             return jsonify({"error": "Email required"}), 400

#         with get_db() as conn:
#             cur = conn.cursor()

#             # Get member
#             cur.execute("""
#                         SELECT id FROM members
#                         WHERE company_id = %s AND email = %s
#                         """, (company_id, email))
#             member = cur.fetchone()

#             if not member:
#                 return jsonify({"error": "Member not found"}), 404

#             member_id = member['id']
#             now = utc_now()

#             # Find open session
#             cur.execute("""
#                         SELECT id, punch_in_time
#                         FROM punch_logs
#                         WHERE company_id = %s
#                           AND member_id = %s
#                           AND punch_out_time IS NULL
#                         ORDER BY punch_in_time DESC
#                             LIMIT 1
#                         """, (company_id, member_id))

#             session = cur.fetchone()

#             if not session:
#                 return jsonify({
#                     "success": True,
#                     "message": "No active session to punch out"
#                 }), 200

#             # --- timezone safety ---
#             punchin_time = ensure_utc(session['punch_in_time'])
#             now = ensure_utc(now)

#             duration_minutes = int((now - punchin_time).total_seconds() // 60)

#             # Update session (race-condition safe)
#             cur.execute("""
#                         UPDATE punch_logs
#                         SET punch_out_time = %s,
#                             duration_minutes = %s,
#                             status = 'punched_out'
#                         WHERE id = %s AND punch_out_time IS NULL
#                             RETURNING id
#                         """, (now, duration_minutes, session['id']))

#             updated = cur.fetchone()
#             if not updated:
#                 return jsonify({"success": True, "message": "Session already closed"}), 200

#             punchlog_id = updated['id']

#             # Update member state
#             cur.execute("""
#                         UPDATE members
#                         SET last_punch_out_at = %s, status = 'offline', is_punched_in = FALSE
#                         WHERE id = %s
#                         """, (now, member_id))

#             conn.commit()

#             return jsonify({
#                 "success": True,
#                 "message": "Punched out successfully",
#                 "punchlogid": punchlog_id,
#                 "duration_minutes": duration_minutes,
#                 "punchouttime": now.isoformat()
#             }), 200

#     except Exception as e:
#         print("❌ PUNCH-OUT ERROR:", e)
#         return jsonify({"error": "Failed to record punch out"}), 500





# # ============================================================================
# # UPLOAD DATA
# # ============================================================================

# # @tracker_bp.route('/tracker/upload', methods=['POST'])
# # @require_tracker_token
# # def tracker_upload():
# #     """Upload tracking data from tracker"""
# #     try:
# #         data = request.get_json(silent=True) or {}
# #         company_id = request.tracker_company_id

# #         email = data.get('email', '').lower().strip()
# #         deviceid_str = data.get('deviceid', '')

# #         if not email or not deviceid_str:
# #             return jsonify({"error": "Email and deviceid required"}), 400

# #         with get_db() as conn:
# #             cur = conn.cursor()

# #             # Get member
# #             cur.execute("SELECT id FROM members WHERE company_id = %s AND email = %s", (company_id, email))
# #             member = cur.fetchone()

# #             if not member:
# #                 return jsonify({"error": "Member not found"}), 404

# #             member_id = member['id']

# #             # Get device
# #             cur.execute(
# #                 "SELECT id FROM devices WHERE company_id = %s AND member_id = %s AND device_id = %s",
# #                 (company_id, member_id, deviceid_str)
# #             )
# #             device = cur.fetchone()

# #             if not device:
# #                 return jsonify({"error": "Device not registered"}), 404

# #             device_db_id = device['id']

# #             now = datetime.utcnow()
# #             today = now.date()
              
# #             # 🔥 CRITICAL FIX — Check punch status first
# #             cur.execute("SELECT is_punched_in FROM members WHERE id = %s", (member_id,))
# #             member_row = cur.fetchone()
# #             is_punched_in = member_row['is_punched_in'] if member_row else False



# #             is_idle = data.get('isidle', False)
# #             is_locked = data.get('locked', False)

# #             # ⭐ STATUS PRIORITY SYSTEM
# #             if not is_punched_in:
# #                   member_status = 'offline'
# #             elif is_locked:
# #                   member_status = 'offline'
# #             elif is_idle:
# #                   member_status = 'idle'
# #             else:
# #                  member_status = 'active'


# #             # ✅ UPDATE MEMBER STATUS
# #             cur.execute("""
# #                  UPDATE members
# #                  SET status = %s,
# #                  last_activity_at = %s,
# #                  last_heartbeat_at = %s
# #                 WHERE id = %s
# #             """, (
# #                  member_status,
# #                  now,
# #                  now,
# #                  member_id
# #             ))

# #             print("STATUS SAVED TO DB:", member_status)

            


# #             screenshot_data = data.get('screenshot')
# #             windows_opened = data.get('windowsopened', [])
# #             browser_history = data.get('browserhistory', [])

# #             # Insert into activity_log
# #             cur.execute("""
# #                 INSERT INTO activity_log (
# #                     company_id, member_id, device_id, timestamp,
# #                     session_start, last_activity, username, email,
# #                     total_seconds, active_seconds, idle_seconds, locked_seconds,
# #                     idle_for, is_idle, locked, mouse_active, keyboard_active,
# #                     current_window, current_process, windows_opened, browser_history, screenshot
# #                 ) VALUES (
# #                     %s, %s, %s, %s, %s, %s, %s, %s,
# #                     %s, %s, %s, %s, %s, %s, %s, %s,
# #                     %s, %s, %s, %s, %s, %s
# #                 ) RETURNING id
# #             """, (
# #                 company_id, member_id, deviceid_str, data.get('timestamp', now),
# #                 data.get('sessionstart'), data.get('lastactivity'), data.get('username'),
# #                 email, data.get('totalseconds', 0),
# #                 data.get('activeseconds', 0), data.get('idleseconds', 0), data.get('lockedseconds', 0),
# #                 data.get('idlefor', 0), is_idle, is_locked, data.get('mouseactive', False),
# #                 data.get('keyboardactive', False), data.get('currentwindow'), data.get('currentprocess'),
# #                 json.dumps(windows_opened), json.dumps(browser_history), screenshot_data
# #             ))

# #             result = cur.fetchone()
# #             raw_data_id = result['id'] if result else None

# #             # Process screenshot if provided
# #             screenshot_id = None
# #             if screenshot_data:
# #                 try:
# #                     if ',' in screenshot_data:
# #                         screenshot_data = screenshot_data.split(',', 1)[1]

# #                     img_data = base64.b64decode(screenshot_data)
# #                     img = Image.open(BytesIO(img_data))

# #                     # Convert to WEBP
# #                     output = BytesIO()
# #                     img.save(output, format='WEBP', quality=80)
# #                     webp_binary = output.getvalue()

# #                     cur.execute("""
# #                         INSERT INTO screenshots (
# #                             company_id, member_id, device_id, raw_data_id, timestamp, tracking_date,
# #                             screenshot_data, file_size, width, height
# #                         ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
# #                         RETURNING id
# #                     """, (
# #                         company_id, member_id, device_db_id, raw_data_id,
# #                         data.get('timestamp', now), today, webp_binary,
# #                         len(webp_binary), img.width, img.height
# #                     ))

# #                     result = cur.fetchone()
# #                     screenshot_id = result['id'] if result else None
# #                     print(f"🔍 Debug: screenshot_id={screenshot_id}, company_id={company_id}, member_id={member_id}")
# #                     print(f"🔍 Debug: SAVE_SCREENSHOTS_TO_FS={SAVE_SCREENSHOTS_TO_FS}, SCREENSHOT_SAVE_PATH={SCREENSHOT_SAVE_PATH}")

# #                     # Validate screenshot (avoid tiny/blank captures)
# #                     try:
# #                         MIN_FILE_SIZE = 1024  # bytes
# #                         MIN_DIM = 100  # pixels
# #                         is_valid = True
# #                         invalid_reason = None
# #                         if len(webp_binary) < MIN_FILE_SIZE or img.width < MIN_DIM or img.height < MIN_DIM:
# #                             is_valid = False
# #                             invalid_reason = 'too_small_or_small_dimensions'
# #                         cur.execute("UPDATE screenshots SET is_valid = %s, invalid_reason = %s WHERE id = %s", (is_valid, invalid_reason, screenshot_id))
# #                     except Exception as e:
# #                         print(f"⚠️ Failed to set validity for screenshot {screenshot_id}: {e}")


# #                     # Save screenshot file to filesystem (optional)
# #                     try:
# #                         if SAVE_SCREENSHOTS_TO_FS and screenshot_id:
# #                             # Optionally only save when member is punched in
# #                             should_save = True
# #                             if SAVE_SCREENSHOTS_ONLY_WHEN_PUNCHED_IN:
# #                                 member_punched = False
# #                                 last_punch_in_at = None
# #                                 try:
# #                                     cur.execute('SELECT is_punched_in, last_punch_in_at FROM members WHERE id = %s', (member_id,))
# #                                     mrow = cur.fetchone()
# #                                     member_punched = bool(mrow and mrow.get('is_punched_in'))
# #                                     last_punch_in_at = mrow.get('last_punch_in_at') if mrow else None
# #                                 except Exception as e:
# #                                     print(f"⚠️ Could not verify member punch-in status: {e}")
# #                                     member_punched = False
# #                                 print(f"🔍 Debug: member_id={member_id} is_punched_in={member_punched}, last_punch_in_at={last_punch_in_at}")

# #                                 # If not currently punched in, allow a short grace window if a recent punch-in exists
# #                                 if not member_punched:
# #                                     try:
# #                                         grace_cutoff = now - timedelta(minutes=2)
# #                                         cur.execute("""
# #                                             SELECT id, timestamp FROM punch_logs
# #                                             WHERE company_id = %s AND member_id = %s
# #                                               AND (action = 'punch_in' OR punch_in_time IS NOT NULL)
# #                                               AND COALESCE(timestamp, punch_in_time) >= %s
# #                                             ORDER BY COALESCE(timestamp, punch_in_time) DESC LIMIT 1
# #                                         """, (company_id, member_id, grace_cutoff))
# #                                         recent_punch = cur.fetchone()
# #                                         if recent_punch:
# #                                             member_punched = True
# #                                             print(f"🔍 Debug: Accepting recent punch-in (grace) for member {member_id}")
# #                                     except Exception as e:
# #                                         print(f"⚠️ Could not check recent punch logs: {e}")

# #                                 should_save = member_punched

# #                             if not should_save:
# #                                 print(f"⚠️ Skipping filesystem save because member not punched in or beyond grace window: member_id={member_id}")
# #                             else:
# #                                 # Directory per company and member helps organization
# #                                 save_root = os.getenv('SCREENSHOT_SAVE_PATH', SCREENSHOT_SAVE_PATH)
# #                                 file_dir = os.path.join(save_root, str(company_id), str(member_id))
# #                                 try:
# #                                     os.makedirs(file_dir, exist_ok=True)
# #                                 except Exception as e:
# #                                     print(f"⚠️ Failed to create screenshot directory '{file_dir}': {e}")

# #                                 # Use UTC timestamp (fall back to now)
# #                                 ts = data.get('timestamp', now)
# #                                 try:
# #                                     ts_str = ts.strftime('%Y%m%d_%H%M%S')
# #                                 except Exception:
# #                                     ts_str = now.strftime('%Y%m%d_%H%M%S')

# #                                 fname = f"screenshot_{screenshot_id}_{ts_str}.webp"
# #                                 fpath = os.path.join(file_dir, fname)
# #                                 print(f"🔍 Debug: Will write to {fpath}")
# #                                 with open(fpath, 'wb') as f:
# #                                     f.write(webp_binary)
# #                                 print(f"✅ Saved screenshot to filesystem: {fpath}")
# #                                 try:
# #                                     # Record that the file was saved on disk
# #                                     cur.execute("UPDATE screenshots SET is_saved_to_fs = TRUE, saved_filename = %s WHERE id = %s", (fpath, screenshot_id))
# #                                 except Exception as e:
# #                                     print(f"⚠️ Failed to update screenshot saved flag for {screenshot_id}: {e}")
# #                         else:
# #                             print(f"⚠️ Not saving to filesystem (SAVE_SCREENSHOTS_TO_FS={SAVE_SCREENSHOTS_TO_FS}, screenshot_id={screenshot_id})")
# #                     except Exception as e:
# #                         print(f"⚠️ Failed to save screenshot to filesystem: {e}")

# #                 except Exception as e:
# #                     print(f"⚠️ Screenshot processing error: {e}")

# #             # Update device status (DISABLED - schema unknown)
# #             # cur.execute("UPDATE devices SET lastseen = %s, status = 'online' WHERE id = %s", (now, device_db_id))
# #             # TODO: Find correct column name for devices table

# #             # Update member status

# #             print("STATUS SAVED TO DB:", member_status)
# #             cur.execute("""
# #                 UPDATE members 
# #                 SET last_activity_at = %s, last_heartbeat_at = %s, status = %s 
# #                 WHERE id = %s
# #             """, (now, now, member_status, member_id))

# #             print(f"✅ UPLOAD: Data uploaded successfully for member {member_id}")

# #             return jsonify({
# #                 "success": True,
# #                 "message": "Data uploaded successfully",
# #                 "rawdataid": raw_data_id,
# #                 "screenshotid": screenshot_id,
# #                 "memberstatus": member_status,
# #                 "trackingdate": today.isoformat()
# #             }), 200

# #     except Exception as e:
# #         print(f"❌ UPLOAD Error: {e}")
# #         import traceback
# #         traceback.print_exc()
# #         return jsonify({"error": "Failed to upload data"}), 500


# @tracker_bp.route('/tracker/upload', methods=['POST'])
# @require_tracker_token
# def tracker_upload():
#     """Upload tracking data from tracker (Cloudinary version)"""
#     try:
#         data = request.get_json(silent=True) or {}
#         company_id = request.tracker_company_id

#         email = data.get('email', '').lower().strip()
#         deviceid_str = data.get('deviceid', '')

#         if not email or not deviceid_str:
#             return jsonify({"error": "Email and deviceid required"}), 400

#         with get_db() as conn:
#             cur = conn.cursor()

#             # ==========================
#             # GET MEMBER
#             # ==========================
#             cur.execute("SELECT id FROM members WHERE company_id = %s AND email = %s",
#                         (company_id, email))
#             member = cur.fetchone()

#             if not member:
#                 return jsonify({"error": "Member not found"}), 404

#             member_id = member['id']

#             # ==========================
#             # GET DEVICE
#             # ==========================
#             cur.execute(
#                 "SELECT id FROM devices WHERE company_id = %s AND member_id = %s AND device_id = %s",
#                 (company_id, member_id, deviceid_str)
#             )
#             device = cur.fetchone()

#             if not device:
#                 return jsonify({"error": "Device not registered"}), 404

#             device_db_id = device['id']

#             # use aware UTC timestamp helper
#             now = utc_now()
#             # convert to IST for tracking_date (dashboard also uses IST)
#             ist = pytz.timezone("Asia/Kolkata")
#             now_ist = now.astimezone(ist)
#             today = now_ist.date()

#             # ==========================
#             # CHECK PUNCH STATUS
#             # ==========================
#             cur.execute("SELECT is_punched_in FROM members WHERE id = %s", (member_id,))
#             member_row = cur.fetchone()
#             is_punched_in = member_row['is_punched_in'] if member_row else False

#             # debug screenshot payload details
#             screenshot_data = data.get('screenshot')
#             print(f"🔍 Screenshot payload present: {bool(screenshot_data)} length={len(screenshot_data) if screenshot_data else 0}")

#             is_idle = data.get('isidle', False)
#             is_locked = data.get('locked', False)

#             if not is_punched_in:
#                 member_status = 'offline'
#             elif is_locked:
#                 member_status = 'offline'
#             elif is_idle:
#                 member_status = 'idle'
#             else:
#                 member_status = 'active'

#             # Update member status
#             cur.execute("""
#                 UPDATE members
#                 SET status = %s,
#                     last_activity_at = %s,
#                     last_heartbeat_at = %s
#                 WHERE id = %s
#             """, (member_status, now, now, member_id))

#             # ==========================
#             # ACTIVITY LOG INSERT
#             # ==========================
#             screenshot_data = data.get('screenshot')
#             windows_opened = data.get('windowsopened', [])
#             browser_history = data.get('browserhistory', [])

#             cur.execute("""
#                 INSERT INTO activity_log (
#                     company_id, member_id, device_id, timestamp,
#                     session_start, last_activity, username, email,
#                     total_seconds, active_seconds, idle_seconds, locked_seconds,
#                     idle_for, is_idle, locked, mouse_active, keyboard_active,
#                     current_window, current_process, windows_opened,
#                     browser_history, screenshot
#                 ) VALUES (
#                     %s, %s, %s, %s, %s, %s, %s, %s,
#                     %s, %s, %s, %s, %s, %s, %s, %s,
#                     %s, %s, %s, %s, %s, %s
#                 ) RETURNING id
#             """, (
#                 company_id, member_id, deviceid_str,
#                 data.get('timestamp', now),
#                 data.get('sessionstart'),
#                 data.get('lastactivity'),
#                 data.get('username'),
#                 email,
#                 data.get('totalseconds', 0),
#                 data.get('activeseconds', 0),
#                 data.get('idleseconds', 0),
#                 data.get('lockedseconds', 0),
#                 data.get('idlefor', 0),
#                 is_idle,
#                 is_locked,
#                 data.get('mouseactive', False),
#                 data.get('keyboardactive', False),
#                 data.get('currentwindow'),
#                 data.get('currentprocess'),
#                 json.dumps(windows_opened),
#                 json.dumps(browser_history),
#                 None  # no binary storage anymore
#             ))

#             result = cur.fetchone()
#             raw_data_id = result['id'] if result else None

#             # ==========================================
#             # SCREENSHOT → CLOUDINARY → DATABASE
#             # ==========================================
#             screenshot_id = None

#             if screenshot_data:
#                 try:
#                     if ',' in screenshot_data:
#                         screenshot_data = screenshot_data.split(',', 1)[1]

#                     img_data = base64.b64decode(screenshot_data)
#                     img = Image.open(BytesIO(img_data))

#                     output = BytesIO()
#                     img.save(output, format='WEBP', quality=70)
#                     webp_binary = output.getvalue()

#                     # Upload to Cloudinary
#                     upload_result = cloudinary.uploader.upload(
#                         webp_binary,
#                         folder=f"workeye/company_{company_id}/member_{member_id}/{today}",
#                         resource_type="image",
#                         format="webp"
#                     )

#                     cloudinary_url = upload_result.get("secure_url")

#                     print(f"☁️ Uploaded to Cloudinary: {cloudinary_url}")

#                     # Save URL in DB
#                     cur.execute("""
#                         INSERT INTO screenshots (
#                             company_id,
#                             member_id,
#                             device_id,
#                             raw_data_id,
#                             timestamp,
#                             tracking_date,
#                             screenshot_url,
#                             file_size,
#                             width,
#                             height
#                         )
#                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#                         RETURNING id
#                     """, (
#                         company_id,
#                         member_id,
#                         device_db_id,
#                         raw_data_id,
#                         data.get('timestamp', now),
#                         today,
#                         cloudinary_url,
#                         len(webp_binary),
#                         img.width,
#                         img.height
#                     ))

#                     result = cur.fetchone()
#                     screenshot_id = result['id'] if result else None
#                     print(f"✅ Screenshot DB row created: id={screenshot_id}, tracking_date={today}")

#                 except Exception as e:
#                     print(f"❌ Screenshot upload failed: {e}")

#             conn.commit()

#             return jsonify({
#                 "success": True,
#                 "message": "Data uploaded successfully",
#                 "rawdataid": raw_data_id,
#                 "screenshotid": screenshot_id,
#                 "memberstatus": member_status,
#                 "trackingdate": today.isoformat()
#             }), 200

#     except Exception as e:
#         print(f"❌ UPLOAD Error: {e}")
#         return jsonify({"error": "Failed to upload data"}), 500
# # ============================================================================
# # HEARTBEAT
# # ============================================================================

# @tracker_bp.route('/tracker/heartbeat', methods=['POST'])
# @require_tracker_token
# def tracker_heartbeat():
#     """Keep-alive ping from tracker"""
#     try:
#         data = request.get_json(silent=True) or {}
#         company_id = request.tracker_company_id

#         email = data.get('email', '').lower().strip()
#         deviceid_str = data.get('deviceid', '')

#         if not email or not deviceid_str:
#             return jsonify({"error": "Email and deviceid required"}), 400

#         with get_db() as conn:
#             cur = conn.cursor()

#             cur.execute("""
#                 UPDATE devices d 
#                 SET last_seen_at = %s, status = 'online'
#                 FROM members m 
#                 WHERE d.company_id = %s AND d.member_id = m.id 
#                   AND m.email = %s AND d.device_id = %s
#             """, (datetime.utcnow(), company_id, email, deviceid_str))

#             return jsonify({"success": True, "message": "Heartbeat received"}), 200

#     except Exception as e:
#         print(f"❌ HEARTBEAT Error: {e}")
#         return jsonify({"error": "Failed to process heartbeat"}), 500


# __all__ = ['tracker_bp']










"""
TRACKER ROUTES - WITH COMPREHENSIVE DEBUGGING
==============================================
Handles all tracker endpoints with detailed logging
"""

from flask import Blueprint, request, jsonify, send_file, after_this_request, current_app
from db import get_db
from datetime import datetime, timedelta
import base64
import json
from PIL import Image
from io import BytesIO
import os
import tempfile
from functools import wraps
from datetime import datetime, timezone
import pytz



# Filesystem save configuration (optional)
# Read from environment: set SAVE_SCREENSHOTS_TO_FS=true and SCREENSHOT_SAVE_PATH to enable
SAVE_SCREENSHOTS_TO_FS = os.getenv('SAVE_SCREENSHOTS_TO_FS', 'true').lower() in ('1','true','yes')
SCREENSHOT_SAVE_PATH = os.getenv('SCREENSHOT_SAVE_PATH', os.path.join(os.getcwd(), 'screenshots'))
# Only save to fs when member is punched in (configurable)
SAVE_SCREENSHOTS_ONLY_WHEN_PUNCHED_IN = os.getenv('SAVE_SCREENSHOTS_ONLY_WHEN_PUNCHED_IN', 'true').lower() in ('1','true','yes')
# Ensure base path exists when enabled
if SAVE_SCREENSHOTS_TO_FS:
    try:
        os.makedirs(SCREENSHOT_SAVE_PATH, exist_ok=True)
    except Exception as e:
        print(f"⚠️ Could not create screenshot base directory '{SCREENSHOT_SAVE_PATH}': {e}")

tracker_bp = Blueprint('tracker', __name__)


def utc_now():
    return datetime.now(timezone.utc)


def ensure_utc(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def verify_tracker_token(token: str):
    try:
        decoded = base64.b64decode(token.encode()).decode()
        return int(decoded.split(':', 1)[0])
    except Exception:
        return None

def emit_member_status_update(company_id, member_id, status):
    """Emit member status update via Socket.IO (best effort)"""
    try:
        # Use the Socket.IO server instance from the main app so we can emit
        # from regular HTTP routes (works from any thread/process where app is imported).
        from app import socketio

        message = {
            'member_id': member_id,
            'status': status,
            'timestamp': datetime.utcnow().isoformat()
        }

        room = f"company_{company_id}"
        socketio.emit('member_status_update', message, room=room, namespace='/')
        print(f"📡 ✅ Emitted member_status_update via Socket.IO: member_id={member_id}, status={status}")

    except RuntimeError as e:
        # emit() can only be called from socket handlers
        print(f"⚠️ Cannot emit from HTTP route: {e}")
        # Status is already updated in database, frontend will fetch it
        print(f"⚠️ Status updated in database: member_id={member_id}, status={status}")
    except Exception as e:
        print(f"⚠️ Failed to emit status update: {e}")
        # Status is still in database, frontend will see it on refresh


def verify_tracker_token(token: str):
    """Verify tracker token and extract company_id"""
    try:
        if not token or not isinstance(token, str):
            print(f"❌ Token is None or not string")
            return None

        decoded = base64.b64decode(token.encode()).decode()
        parts = decoded.split(':', 1)

        if len(parts) >= 1:
            company_id = int(parts[0])
            print(f"✅ Token decoded: company_id={company_id}")
            return company_id

        return None
    except Exception as e:
        print(f"❌ Token verification error: {e}")
        return None


def require_tracker_token(f):
    """Decorator: Require tracker token authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from header
        tracker_token = request.headers.get('X-Tracker-Token')

        if not tracker_token:
            # Try to get from body
            try:
                data = request.get_json(silent=True) or {}
                tracker_token = data.get('tracker_token')
            except:
                pass

        if not tracker_token:
            print("❌ No tracker token provided in request")
            return jsonify({"error": "Tracker token required"}), 401

        # Verify token and get company_id
        company_id = verify_tracker_token(tracker_token)

        if not company_id:
            print(f"❌ Invalid tracker token format")
            return jsonify({"error": "Invalid tracker token"}), 401

        try:
            with get_db() as conn:
                cur = conn.cursor()

                # Check what columns exist in companies table
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'companies'
                """)
                company_cols = [row['column_name'] for row in cur.fetchall()]
                print(f"✅ Companies table columns: {company_cols}")

                # Build query based on available columns
                select_cols = ['id']

                # Detect name column
                if 'company_name' in company_cols:
                    select_cols.append('company_name as name')
                elif 'name' in company_cols:
                    select_cols.append('name')
                elif 'companyname' in company_cols:
                    select_cols.append('companyname as name')

                # Add tracker_token if exists
                if 'tracker_token' in company_cols:
                    select_cols.append('tracker_token')

                # FIXED: Detect is_active column properly
                if 'is_active' in company_cols:
                    isactive_col = 'is_active'
                elif 'isactive' in company_cols:
                    isactive_col = 'isactive'
                else:
                    isactive_col = 'is_active'  # Default fallback

                # Build and execute query with detected column name
                query = f"SELECT {', '.join(select_cols)} FROM companies WHERE id = %s AND {isactive_col} = TRUE"
                print(f"🔍 Token verification query: {query}")

                cur.execute(query, (company_id,))
                company = cur.fetchone()

                if not company:
                    print(f"❌ Company {company_id} not found or inactive")
                    return jsonify({"error": "Invalid or inactive company"}), 401

                # Optionally verify tracker_token matches if column exists
                if 'tracker_token' in company_cols and company.get('tracker_token'):
                    if company['tracker_token'] != tracker_token:
                        print(f"❌ Tracker token mismatch for company {company_id}")
                        return jsonify({"error": "Invalid tracker token"}), 401

                company_name = company.get('name', 'Unknown')
                print(f"✅ Token verified for company {company_id}: {company_name}")

        except Exception as e:
            print(f"❌ Database error during token verification: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": "Authentication failed"}), 500

        # Store company_id in request for use in endpoint
        request.tracker_company_id = company_id
        request.tracker_token = tracker_token

        return f(*args, **kwargs)

    return decorated_function



# ============================================================================
# TRACKER DOWNLOAD
# ============================================================================

@tracker_bp.route('/api/tracker/download', methods=['GET'])
def download_tracker():
    """Download tracker with embedded company token"""
    try:
        # Get JWT token from Authorization header
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "Authentication required. Please log in."}), 401

        jwt_token = auth_header.replace('Bearer ', '').strip()

        # Verify admin JWT
        from admin_auth_routes import verify_admin_jwt

        try:
            payload = verify_admin_jwt(jwt_token)
            admin_id = payload['admin_id']
            company_id = payload['company_id']
            admin_email = payload['email']
        except Exception as e:
            print(f"❌ JWT verification failed: {e}")
            return jsonify({"error": f"Authentication failed: {str(e)}"}), 401

        print(f"✅ Tracker download request from admin: {admin_email}, company: {company_id}")

        with get_db() as conn:
            cur = conn.cursor()

            # Check companies table columns
            cur.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'companies'
            """)
            company_cols = [row['column_name'] for row in cur.fetchall()]
            print(f"📋 Companies table columns: {company_cols}")

            # FIXED: Properly detect column names with underscores
            # Check for company_name (with underscore), companyname (without), or name
            if 'company_name' in company_cols:
                name_col = 'company_name'
            elif 'companyname' in company_cols:
                name_col = 'companyname'
            else:
                name_col = 'name'

            print(f"✅ Using company name column: {name_col}")

            # Build select query
            select_cols = ['id', f'{name_col} as companyname']

            if 'tracker_token' in company_cols:
                select_cols.append('tracker_token')
                has_tracker_token = True
            else:
                has_tracker_token = False

            # Determine isactive column name
            if 'is_active' in company_cols:
                isactive_col = 'is_active'
            elif 'isactive' in company_cols:
                isactive_col = 'isactive'
            else:
                isactive_col = 'is_active'  # Default fallback

            query = f"SELECT {', '.join(select_cols)} FROM companies WHERE id = %s AND {isactive_col} = TRUE"
            print(f"🔍 Executing query: {query}")

            cur.execute(query, (company_id,))
            company = cur.fetchone()

            if not company:
                return jsonify({"error": "Company not found or inactive"}), 404

            company_name = company['companyname']

            # Get or generate tracker token
            if has_tracker_token and company.get('tracker_token'):
                tracker_token = company['tracker_token']
                print(f"✅ Using existing tracker_token for company {company_id}")
            else:
                # Generate token
                import secrets
                token_data = f"{company_id}:{secrets.token_urlsafe(32)}"
                tracker_token = base64.b64encode(token_data.encode()).decode()
                print(f"✅ Generated new tracker_token for company {company_id}")

                # Try to save it if column exists
                if has_tracker_token:
                    try:
                        cur.execute("UPDATE companies SET tracker_token = %s WHERE id = %s", (tracker_token, company_id))
                        conn.commit()
                        print(f"✅ Saved tracker_token to database")
                    except Exception as e:
                        print(f"⚠️ Could not save tracker_token: {e}")

            # FIXED: Try multiple possible locations for tracker file
            backend_dir = os.path.dirname(os.path.abspath(__file__))

            # List of possible paths to check
            possible_paths = [
                os.path.join(backend_dir, 'wkv0.0.py'),  # Same directory as tracker_routes.py
                os.path.join(os.getcwd(), 'wkv0.0.py'),  # Current working directory
                os.path.join(backend_dir, '..', 'wkv0.0.py'),  # Parent directory
                '/opt/render/project/src/wkv0.0.py',  # Render deployment path
                'wkv0.0.py',  # Relative path
            ]

            tracker_file_path = None

            print(f"🔍 Searching for wkv0.0.py...")
            print(f"📂 Backend dir: {backend_dir}")
            print(f"📂 Current working dir: {os.getcwd()}")

            try:
                files_in_dir = os.listdir(backend_dir)
                print(f"📂 Files in backend dir ({len(files_in_dir)} total): {files_in_dir[:15]}")
            except Exception as e:
                print(f"⚠️ Could not list backend dir: {e}")

            for path in possible_paths:
                print(f"   Checking: {path}")
                if os.path.exists(path):
                    tracker_file_path = path
                    print(f"✅ Found tracker file at: {path}")
                    break

            if not tracker_file_path:
                print(f"❌ Tracker template not found in any location!")
                return jsonify({
                    "error": "Tracker template file not found on server",
                    "details": "wkv0.0.py file is missing. Please ensure it's uploaded to the backend repository.",
                    "searched_paths": possible_paths
                }), 500

            with open(tracker_file_path, 'r', encoding='utf-8') as f:
                tracker_content = f.read()

            print(f"✅ Tracker file read successfully ({len(tracker_content)} bytes)")

            # Inject token and company_id
            replacements = {
                "'tracker_token': None": f"'tracker_token': '{tracker_token}'",
                '"tracker_token": None': f'"tracker_token": "{tracker_token}"',
                "'company_id': None": f"'company_id': {company_id}",
                '"company_id": None': f'"company_id": {company_id}',
            }

            for old_value, new_value in replacements.items():
                if old_value in tracker_content:
                    tracker_content = tracker_content.replace(old_value, new_value)
                    print(f"✅ Replaced: {old_value[:30]}...")

            # Add header comment
            header_comment = f'''"""
╔═══════════════════════════════════════════════════════════════╗
║                    WORK-EYE TRACKER                           ║
║              Pre-Configured for {company_name[:30].ljust(30)} ║
╠═══════════════════════════════════════════════════════════════╣
║  Company ID: {str(company_id).ljust(48)} ║
║  Token: ***{tracker_token[-8:].ljust(45)} ║
║  Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC').ljust(45)} ║
╠═══════════════════════════════════════════════════════════════╣
║  INSTRUCTIONS:                                                ║
║  1. Run this file on employee computer                        ║
║  2. Employee enters their registered email                    ║
║  3. Tracker automatically verifies and starts                 ║
╚═══════════════════════════════════════════════════════════════╝
"""

'''
            tracker_content = header_comment + tracker_content

            # Save to temp file
            temp_fd, temp_file_path = tempfile.mkstemp(suffix='.py', prefix='workeye_tracker_')

            with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_file:
                temp_file.write(tracker_content)

            # Sanitize company name for filename
            sanitized_company = ''.join(c for c in company_name if c.isalnum() or c in [' ', '-', '_']).strip()
            sanitized_company = sanitized_company.replace(' ', '_')
            output_filename = f"WorkEyeTracker_{sanitized_company}.py"

            @after_this_request
            def cleanup(response):
                try:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                except Exception as e:
                    print(f"⚠️ Failed to cleanup temp file: {e}")
                return response

            print(f"✅ Tracker generated successfully: {output_filename}")

            return send_file(
                temp_file_path,
                mimetype='text/x-python',
                as_attachment=True,
                download_name=output_filename
            )

    except Exception as e:
        print(f"❌ Tracker download error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to generate tracker", "details": str(e)}), 500




# ============================================================================
# VERIFY MEMBER
# ============================================================================

@tracker_bp.route('/tracker/verify-member', methods=['POST'])
@require_tracker_token
def verify_member():
    """Verify member email and register device"""
    try:
        data = request.get_json(silent=True) or {}
        company_id = request.tracker_company_id

        email = data.get('email', '').lower().strip()
        deviceid = data.get('deviceid', '')

        print("="*70)
        print("🔍 VERIFY MEMBER START")
        print("="*70)
        print(f"📧 Email: '{email}'")
        print(f"🏢 Company ID: {company_id}")
        print(f"💻 Device ID: {deviceid}")

        if not email:
            print("❌ Email is required but not provided")
            return jsonify({"error": "Email required"}), 400

        if not deviceid:
            print("❌ Device ID is required but not provided")
            return jsonify({"error": "Device ID required"}), 400

        with get_db() as conn:
            cur = conn.cursor()

            # Check members table columns
            cur.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'members'
            """)
            member_cols = [row['column_name'] for row in cur.fetchall()]
            print(f"✅ Members table columns: {member_cols}")

            # Determine name column
            if 'full_name' in member_cols:
                name_col = 'full_name'
            elif 'name' in member_cols:
                name_col = 'name'
            elif 'fullname' in member_cols:
                name_col = 'fullname'
            else:
                print("❌ No name column found in members table!")
                return jsonify({"error": "Database configuration error"}), 500

            # Determine company_id column
            if 'company_id' in member_cols:
                company_col = 'company_id'
            elif 'companyid' in member_cols:
                company_col = 'companyid'
            else:
                company_col = 'company_id'

            # Determine is_active column
            if 'is_active' in member_cols:
                active_col = 'is_active'
            elif 'isactive' in member_cols:
                active_col = 'isactive'
            else:
                active_col = 'is_active'

            print(f"✅ Using columns: name={name_col}, company={company_col}, active={active_col}")

            # Query for member
            query = f"""
                SELECT id, email, {name_col} as membername, position, {active_col} as isactive 
                FROM members 
                WHERE {company_col} = %s AND email = %s
            """
            print(f"🔍 Executing query: {query}")
            print(f"🔍 Parameters: {company_col}={company_id}, email='{email}'")

            cur.execute(query, (company_id, email))
            member = cur.fetchone()

            if not member:
                print("❌ Member NOT FOUND!")

                # Debug: Check total members for this company
                cur.execute(f"SELECT COUNT(*) as count FROM members WHERE {company_col} = %s", (company_id,))
                count = cur.fetchone()['count']
                print(f"📊 Total members for company {company_id}: {count}")

                # Debug: List all members for this company
                cur.execute(f"SELECT id, email, {name_col} as name FROM members WHERE {company_col} = %s LIMIT 5", (company_id,))
                all_members = cur.fetchall()
                print(f"📋 Existing members:")
                for m in all_members:
                    print(f"   - ID: {m['id']}, Email: '{m['email']}', Name: {m['name']}")

                return jsonify({
                    "error": f"Email '{email}' not found in company. Contact your admin.",
                    "debug_info": f"Total members in company: {count}"
                }), 404

            print("✅ Member FOUND!")
            print(f"   - Member ID: {member['id']}")
            print(f"   - Member Name: {member['membername']}")
            print(f"   - Member Position: {member.get('position', 'N/A')}")
            print(f"   - Member Active: {member.get('isactive', True)}")

            # Check if member is active
            if not member.get('isactive', True):
                print("❌ Member account is INACTIVE")
                return jsonify({"error": "Member account is inactive"}), 403

            member_id = member['id']
            member_name = member.get('membername', 'Unknown')

            # Register/update device
            print("💻 Checking devices table...")

            # Check devices table columns
            cur.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'devices'
            """)
            device_cols = [row['column_name'] for row in cur.fetchall()]
            print(f"✅ Devices table columns: {device_cols}")

            # Determine device column names
            if 'company_id' in device_cols:
                dev_company_col = 'company_id'
                dev_member_col = 'member_id'
                dev_device_col = 'device_id'
                dev_name_col = 'device_name'
            else:
                dev_company_col = 'companyid'
                dev_member_col = 'memberid'
                dev_device_col = 'deviceid'
                dev_name_col = 'devicename'

            print(f"✅ Using device columns: {dev_company_col}, {dev_member_col}, {dev_device_col}")

            cur.execute(f"""
                SELECT id, {dev_name_col} as devicename, status 
                FROM devices 
                WHERE {dev_company_col} = %s AND {dev_member_col} = %s AND {dev_device_col} = %s
            """, (company_id, member_id, deviceid))

            device = cur.fetchone()

            if device:
                device_db_id = device['id']
                print(f"✅ Existing device found (DB ID: {device_db_id})")

                # Update device member_id if needed (device can be reassigned to new member)
                hostname = data.get('hostname', 'Unknown')
                osinfo = data.get('osinfo', 'Unknown OS')

                if 'os_info' in device_cols:
                    osinfo_col = 'os_info'
                elif 'osinfo' in device_cols:
                    osinfo_col = 'osinfo'
                else:
                    osinfo_col = 'os_info'

                cur.execute(f"""
                    UPDATE devices 
                    SET {dev_member_col} = %s, 
                        {dev_name_col} = %s, 
                        hostname = %s, 
                        {osinfo_col} = %s,
                        last_seen_at = NOW(),
                        status = 'active'
                    WHERE id = %s
                """, (member_id, hostname, hostname, osinfo, device_db_id))
                print(f"✅ Device updated with current member and status")
            else:
                # Register new device
                print("💻 Registering new device...")
                hostname = data.get('hostname', 'Unknown')
                osinfo = data.get('osinfo', 'Unknown OS')

                # FIXED: Detect os_info column name
                if 'os_info' in device_cols:
                    osinfo_col = 'os_info'
                elif 'osinfo' in device_cols:
                    osinfo_col = 'osinfo'
                else:
                    osinfo_col = 'os_info'

                print(f"✅ Using osinfo column: {osinfo_col}")

                # Check if device exists for any member in this company (handle reassignment)
                cur.execute(f"""
                    SELECT id, {dev_member_col} as current_member_id 
                    FROM devices 
                    WHERE {dev_company_col} = %s AND {dev_device_col} = %s
                """, (company_id, deviceid))

                existing_device = cur.fetchone()

                if existing_device:
                    # Device exists but for different member - reassign it
                    device_db_id = existing_device['id']
                    print(f"💻 Device exists for another member, reassigning...")

                    cur.execute(f"""
                        UPDATE devices 
                        SET {dev_member_col} = %s, 
                            {dev_name_col} = %s, 
                            hostname = %s, 
                            {osinfo_col} = %s,
                            last_seen_at = NOW(),
                            status = 'active'
                        WHERE id = %s
                    """, (member_id, hostname, hostname, osinfo, device_db_id))
                    print(f"✅ Device reassigned to current member (DB ID: {device_db_id})")
                else:
                    # Truly new device - insert it
                    cur.execute(f"""
                        INSERT INTO devices ({dev_company_col}, {dev_member_col}, {dev_device_col}, {dev_name_col}, hostname, {osinfo_col}, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'active')
                        RETURNING id
                    """, (company_id, member_id, deviceid, hostname, hostname, osinfo))

                    result = cur.fetchone()
                    device_db_id = result['id'] if result else None

                    if device_db_id:
                        print(f"✅ New device registered (DB ID: {device_db_id})")
                    else:
                        print("⚠️ Device registration returned no ID")


            print("="*70)
            print("✅ VERIFY SUCCESS!")
            print(f"👤 Member: {member_name} ({email})")
            print(f"💻 Device: {device_db_id}")
            print("="*70)

            return jsonify({
                "success": True,
                "message": "Member verified successfully",
                "member": {
                    "id": member_id,
                    "email": member['email'],
                    "name": member_name,
                    "fullname": member_name,
                    "position": member.get('position', 'Member')
                },
                "device_id": device_db_id
            }), 200

    except Exception as e:
        print(f"❌ VERIFY EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": "Internal server error during verification",
            "details": str(e)
        }), 500





# ==============================
# PUNCH IN
# ==============================

@tracker_bp.route('/tracker/punch-in', methods=['POST'])
@require_tracker_token
def tracker_punch_in():
    """Record punch in (session-based design)"""
    try:
        print("Updated punch in 2")
        data = request.get_json(silent=True) or {}
        company_id = request.tracker_company_id
        email = data.get('email', '').lower().strip()
        deviceid = data.get('deviceid', '')

        if not email or not deviceid:
            return jsonify({"error": "Email and deviceid required"}), 400

        with get_db() as conn:
            cur = conn.cursor()

            # Get member
            cur.execute("""
                        SELECT id FROM members
                        WHERE company_id = %s AND email = %s
                        """, (company_id, email))
            member = cur.fetchone()

            if not member:
                return jsonify({"error": "Member not found"}), 404

            member_id = member['id']

            # Check existing open session
            cur.execute("""
                        SELECT id FROM punch_logs
                        WHERE company_id = %s AND member_id = %s AND punch_out_time IS NULL
                        ORDER BY punch_in_time DESC
                            LIMIT 1
                        """, (company_id, member_id))

            existing = cur.fetchone()
            if existing:
                return jsonify({
                    "success": True,
                    "message": "Already punched in",
                    "punchlogid": existing['id']
                }), 200

            now = utc_now()                           # aware UTC
            ist = pytz.timezone("Asia/Kolkata")

            now_ist = now.astimezone(ist)             # ✅ real conversion
            now_db = now_ist.replace(tzinfo=None)     # optional: naive IST for DB


            cur.execute("""
                        SELECT id FROM devices
                        WHERE company_id = %s AND member_id = %s AND device_id = %s
                        """, (company_id, member_id, deviceid))

            device = cur.fetchone()
            device_db_id = int(device['id'])

            print("device id type: ", type(device_db_id))
            print("deviceid: ",device_db_id)

            # Insert new session row
            cur.execute("""
                        INSERT INTO punch_logs (
                            company_id, member_id, device_id,
                            punch_in_time, punch_date, status
                        )
                        VALUES (%s, %s, %s, %s, %s, 'punched_in')
                            RETURNING id
                        """, (company_id, member_id, device_db_id, now, now_db.date()))

            punchlog_id = cur.fetchone()['id']

            # Update member state
            cur.execute("""
                        UPDATE members
                        SET last_punch_in_at = %s, status = 'active', is_punched_in = TRUE
                        WHERE id = %s
                        """, (now_db, member_id))

            conn.commit()

            return jsonify({
                "success": True,
                "message": "Punched in successfully",
                "punchlogid": punchlog_id,
                "punchintime": now.isoformat()
            }), 200

    except Exception as e:
        print("❌ PUNCH-IN ERROR:", e)
        return jsonify({"error": "Failed to record punch in"}), 500



# ============================================================================
# PUNCH OUT
# ============================================================================

@tracker_bp.route('/tracker/punch-out', methods=['POST'])
@require_tracker_token
def tracker_punch_out():
    """Record punch out (updates existing session row)"""
    try:
        print("Updated punch out 2")
        data = request.get_json(silent=True) or {}
        company_id = request.tracker_company_id

        email = data.get('email', '').lower().strip()

        if not email:
            return jsonify({"error": "Email required"}), 400

        with get_db() as conn:
            cur = conn.cursor()

            # Get member
            cur.execute("""
                        SELECT id FROM members
                        WHERE company_id = %s AND email = %s
                        """, (company_id, email))
            member = cur.fetchone()

            if not member:
                return jsonify({"error": "Member not found"}), 404

            member_id = member['id']
            now = utc_now()

            # Find open session
            cur.execute("""
                        SELECT id, punch_in_time
                        FROM punch_logs
                        WHERE company_id = %s
                          AND member_id = %s
                          AND punch_out_time IS NULL
                        ORDER BY punch_in_time DESC
                            LIMIT 1
                        """, (company_id, member_id))

            session = cur.fetchone()

            if not session:
                return jsonify({
                    "success": True,
                    "message": "No active session to punch out"
                }), 200

            # --- timezone safety ---
            punchin_time = ensure_utc(session['punch_in_time'])
            now = ensure_utc(now)

            duration_minutes = int((now - punchin_time).total_seconds() // 60)

            # Update session (race-condition safe)
            cur.execute("""
                        UPDATE punch_logs
                        SET punch_out_time = %s,
                            duration_minutes = %s,
                            status = 'punched_out'
                        WHERE id = %s AND punch_out_time IS NULL
                            RETURNING id
                        """, (now, duration_minutes, session['id']))

            updated = cur.fetchone()
            if not updated:
                return jsonify({"success": True, "message": "Session already closed"}), 200

            punchlog_id = updated['id']

            # Update member state
            cur.execute("""
                        UPDATE members
                        SET last_punch_out_at = %s, status = 'offline', is_punched_in = FALSE
                        WHERE id = %s
                        """, (now, member_id))

            conn.commit()

            return jsonify({
                "success": True,
                "message": "Punched out successfully",
                "punchlogid": punchlog_id,
                "duration_minutes": duration_minutes,
                "punchouttime": now.isoformat()
            }), 200

    except Exception as e:
        print("❌ PUNCH-OUT ERROR:", e)
        return jsonify({"error": "Failed to record punch out"}), 500





# ============================================================================
# UPLOAD DATA
# ============================================================================

@tracker_bp.route('/tracker/upload', methods=['POST'])
@require_tracker_token
def tracker_upload():
    """Upload tracking data from tracker"""
    try:
        data = request.get_json(silent=True) or {}
        company_id = request.tracker_company_id

        email = data.get('email', '').lower().strip()
        deviceid_str = data.get('deviceid', '')

        if not email or not deviceid_str:
            return jsonify({"error": "Email and deviceid required"}), 400

        with get_db() as conn:
            cur = conn.cursor()

            # Get member
            cur.execute("SELECT id FROM members WHERE company_id = %s AND email = %s", (company_id, email))
            member = cur.fetchone()

            if not member:
                return jsonify({"error": "Member not found"}), 404

            member_id = member['id']

            # Get device
            cur.execute(
                "SELECT id FROM devices WHERE company_id = %s AND member_id = %s AND device_id = %s",
                (company_id, member_id, deviceid_str)
            )
            device = cur.fetchone()

            if not device:
                return jsonify({"error": "Device not registered"}), 404

            device_db_id = device['id']

            now = datetime.utcnow()
            today = now.date()
              
            # 🔥 CRITICAL FIX — Check punch status first
            cur.execute("SELECT is_punched_in FROM members WHERE id = %s", (member_id,))
            member_row = cur.fetchone()
            is_punched_in = member_row['is_punched_in'] if member_row else False



            is_idle = data.get('isidle', False)
            is_locked = data.get('locked', False)

            # ⭐ STATUS PRIORITY SYSTEM
            if not is_punched_in:
                  member_status = 'offline'
            elif is_locked:
                  member_status = 'offline'
            elif is_idle:
                  member_status = 'idle'
            else:
                 member_status = 'active'


            # ✅ UPDATE MEMBER STATUS
            cur.execute("""
                 UPDATE members
                 SET status = %s,
                 last_activity_at = %s,
                 last_heartbeat_at = %s
                WHERE id = %s
            """, (
                 member_status,
                 now,
                 now,
                 member_id
            ))

            print("STATUS SAVED TO DB:", member_status)

            


            screenshot_data = data.get('screenshot')
            windows_opened = data.get('windowsopened', [])
            browser_history = data.get('browserhistory', [])

            # Insert into activity_log
            cur.execute("""
                INSERT INTO activity_log (
                    company_id, member_id, device_id, timestamp,
                    session_start, last_activity, username, email,
                    total_seconds, active_seconds, idle_seconds, locked_seconds,
                    idle_for, is_idle, locked, mouse_active, keyboard_active,
                    current_window, current_process, windows_opened, browser_history, screenshot
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                company_id, member_id, deviceid_str, data.get('timestamp', now),
                data.get('sessionstart'), data.get('lastactivity'), data.get('username'),
                email, data.get('totalseconds', 0),
                data.get('activeseconds', 0), data.get('idleseconds', 0), data.get('lockedseconds', 0),
                data.get('idlefor', 0), is_idle, is_locked, data.get('mouseactive', False),
                data.get('keyboardactive', False), data.get('currentwindow'), data.get('currentprocess'),
                json.dumps(windows_opened), json.dumps(browser_history), screenshot_data
            ))

            result = cur.fetchone()
            raw_data_id = result['id'] if result else None

            # Process screenshot if provided
            screenshot_id = None
            if screenshot_data:
                try:
                    if ',' in screenshot_data:
                        screenshot_data = screenshot_data.split(',', 1)[1]

                    img_data = base64.b64decode(screenshot_data)
                    img = Image.open(BytesIO(img_data))

                    # Convert to WEBP
                    output = BytesIO()
                    img.save(output, format='WEBP', quality=80)
                    webp_binary = output.getvalue()

                    # store as base64 string because screenshots.screenshot_data is TEXT
                    webp_b64 = base64.b64encode(webp_binary).decode('ascii')

                    try:
                        # convert to data URL so frontend can render if needed
                        screenshot_url = f"data:image/webp;base64,{webp_b64}"

                        cur.execute("""
                            INSERT INTO screenshots (
                                company_id, member_id, device_id, raw_data_id, timestamp, tracking_date,
                                screenshot_url, file_size, width, height
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                            company_id, member_id, device_db_id, raw_data_id,
                            data.get('timestamp', now), today, screenshot_url,
                            len(webp_binary), img.width, img.height
                        ))

                        result = cur.fetchone()
                        screenshot_id = result['id'] if result else None
                        print(f"🔍 Debug: screenshot_id={screenshot_id}, company_id={company_id}, member_id={member_id}")
                    except Exception as db_e:
                        # log and continue; upload should not fail because of screenshot
                        print(f"⚠️ Screenshot DB insert failed: {db_e}")
                        screenshot_id = None

                    print(f"🔍 Debug: SAVE_SCREENSHOTS_TO_FS={SAVE_SCREENSHOTS_TO_FS}, SCREENSHOT_SAVE_PATH={SCREENSHOT_SAVE_PATH}")

                    # Validate screenshot (avoid tiny/blank captures)
                    try:
                        MIN_FILE_SIZE = 1024  # bytes
                        MIN_DIM = 100  # pixels
                        is_valid = True
                        invalid_reason = None
                        if len(webp_binary) < MIN_FILE_SIZE or img.width < MIN_DIM or img.height < MIN_DIM:
                            is_valid = False
                            invalid_reason = 'too_small_or_small_dimensions'
                        cur.execute("UPDATE screenshots SET is_valid = %s, invalid_reason = %s WHERE id = %s", (is_valid, invalid_reason, screenshot_id))
                    except Exception as e:
                        print(f"⚠️ Failed to set validity for screenshot {screenshot_id}: {e}")


                    # Save screenshot file to filesystem (optional)
                    try:
                        if SAVE_SCREENSHOTS_TO_FS and screenshot_id:
                            # Optionally only save when member is punched in
                            should_save = True
                            if SAVE_SCREENSHOTS_ONLY_WHEN_PUNCHED_IN:
                                member_punched = False
                                last_punch_in_at = None
                                try:
                                    cur.execute('SELECT is_punched_in, last_punch_in_at FROM members WHERE id = %s', (member_id,))
                                    mrow = cur.fetchone()
                                    member_punched = bool(mrow and mrow.get('is_punched_in'))
                                    last_punch_in_at = mrow.get('last_punch_in_at') if mrow else None
                                except Exception as e:
                                    print(f"⚠️ Could not verify member punch-in status: {e}")
                                    member_punched = False
                                print(f"🔍 Debug: member_id={member_id} is_punched_in={member_punched}, last_punch_in_at={last_punch_in_at}")

                                # If not currently punched in, allow a short grace window if a recent punch-in exists
                                if not member_punched:
                                    try:
                                        grace_cutoff = now - timedelta(minutes=2)
                                        cur.execute("""
                                            SELECT id, timestamp FROM punch_logs
                                            WHERE company_id = %s AND member_id = %s
                                              AND (action = 'punch_in' OR punch_in_time IS NOT NULL)
                                              AND COALESCE(timestamp, punch_in_time) >= %s
                                            ORDER BY COALESCE(timestamp, punch_in_time) DESC LIMIT 1
                                        """, (company_id, member_id, grace_cutoff))
                                        recent_punch = cur.fetchone()
                                        if recent_punch:
                                            member_punched = True
                                            print(f"🔍 Debug: Accepting recent punch-in (grace) for member {member_id}")
                                    except Exception as e:
                                        print(f"⚠️ Could not check recent punch logs: {e}")

                                should_save = member_punched

                            if not should_save:
                                print(f"⚠️ Skipping filesystem save because member not punched in or beyond grace window: member_id={member_id}")
                            else:
                                # Directory per company and member helps organization
                                save_root = os.getenv('SCREENSHOT_SAVE_PATH', SCREENSHOT_SAVE_PATH)
                                file_dir = os.path.join(save_root, str(company_id), str(member_id))
                                try:
                                    os.makedirs(file_dir, exist_ok=True)
                                except Exception as e:
                                    print(f"⚠️ Failed to create screenshot directory '{file_dir}': {e}")

                                # Use UTC timestamp (fall back to now)
                                ts = data.get('timestamp', now)
                                try:
                                    ts_str = ts.strftime('%Y%m%d_%H%M%S')
                                except Exception:
                                    ts_str = now.strftime('%Y%m%d_%H%M%S')

                                fname = f"screenshot_{screenshot_id}_{ts_str}.webp"
                                fpath = os.path.join(file_dir, fname)
                                print(f"🔍 Debug: Will write to {fpath}")
                                with open(fpath, 'wb') as f:
                                    f.write(webp_binary)
                                print(f"✅ Saved screenshot to filesystem: {fpath}")
                                try:
                                    # Record that the file was saved on disk
                                    cur.execute("UPDATE screenshots SET is_saved_to_fs = TRUE, saved_filename = %s WHERE id = %s", (fpath, screenshot_id))
                                except Exception as e:
                                    print(f"⚠️ Failed to update screenshot saved flag for {screenshot_id}: {e}")
                        else:
                            print(f"⚠️ Not saving to filesystem (SAVE_SCREENSHOTS_TO_FS={SAVE_SCREENSHOTS_TO_FS}, screenshot_id={screenshot_id})")
                    except Exception as e:
                        print(f"⚠️ Failed to save screenshot to filesystem: {e}")

                except Exception as e:
                    print(f"⚠️ Screenshot processing error: {e}")

            # Update device status (DISABLED - schema unknown)
            # cur.execute("UPDATE devices SET lastseen = %s, status = 'online' WHERE id = %s", (now, device_db_id))
            # TODO: Find correct column name for devices table

            # Update member status

            print("STATUS SAVED TO DB:", member_status)
            cur.execute("""
                UPDATE members 
                SET last_activity_at = %s, last_heartbeat_at = %s, status = %s 
                WHERE id = %s
            """, (now, now, member_status, member_id))

            print(f"✅ UPLOAD: Data uploaded successfully for member {member_id}")

            return jsonify({
                "success": True,
                "message": "Data uploaded successfully",
                "rawdataid": raw_data_id,
                "screenshotid": screenshot_id,
                "memberstatus": member_status,
                "trackingdate": today.isoformat()
            }), 200

    except Exception as e:
        print(f"❌ UPLOAD Error: {e}")
        import traceback
        traceback.print_exc()
        # include exception message in response to aid debugging (remove in production)
        return jsonify({"error": "Failed to upload data", "details": str(e)}), 500


# ============================================================================
# HEARTBEAT
# ============================================================================

@tracker_bp.route('/tracker/heartbeat', methods=['POST'])
@require_tracker_token
def tracker_heartbeat():
    """Keep-alive ping from tracker"""
    try:
        data = request.get_json(silent=True) or {}
        company_id = request.tracker_company_id

        email = data.get('email', '').lower().strip()
        deviceid_str = data.get('deviceid', '')

        if not email or not deviceid_str:
            return jsonify({"error": "Email and deviceid required"}), 400

        with get_db() as conn:
            cur = conn.cursor()

            cur.execute("""
                UPDATE devices d 
                SET last_seen_at = %s, status = 'online'
                FROM members m 
                WHERE d.company_id = %s AND d.member_id = m.id 
                  AND m.email = %s AND d.device_id = %s
            """, (datetime.utcnow(), company_id, email, deviceid_str))

            return jsonify({"success": True, "message": "Heartbeat received"}), 200

    except Exception as e:
        print(f"❌ HEARTBEAT Error: {e}")
        return jsonify({"error": "Failed to process heartbeat"}), 500


__all__ = ['tracker_bp']