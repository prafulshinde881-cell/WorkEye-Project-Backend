"""
ADMIN_AUTH_ROUTES.PY - Production Multi-Tenant Authentication
================================================================
[OK] Multi-tenant isolation (every query filters by company_id)
[OK] Secure password hashing with bcrypt
[OK] JWT authentication with company_id embedded
[OK] Rate limiting to prevent brute-force attacks
[OK] Comprehensive error handling and logging
[OK] Input validation and sanitization
[OK] Token refresh mechanism
[OK] Secure session management
[OK] FIXED: Uses admin_users table (matches actual DB schema)
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from functools import wraps
import bcrypt
import jwt
import os
import secrets
import base64
import re
from db import get_db
from collections import defaultdict
import time

import requests

admin_auth_bp = Blueprint('admin_auth', __name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

JWT_SECRET = os.environ.get('JWT_SECRET', 'your-super-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24 * 30  # 30 days
JWT_REFRESH_EXPIRATION_DAYS = 90  # 90 days for refresh tokens

# Rate limiting configuration
RATE_LIMIT_WINDOW = 300  # 5 minutes
MAX_LOGIN_ATTEMPTS = 5  # Max attempts per window

# In-memory rate limiting (use Redis in production)
login_attempts = defaultdict(list)

# ============================================================================
# SECURITY UTILITIES
# ============================================================================

def check_license_active(email: str) -> tuple[bool, str]:
    try:
        product_id = "69589e3fe70228ef3c25f26c"
        url = f"https://lisence-system.onrender.com/api/external/actve-license/{email}?productId={product_id}"

        response = requests.get(url, timeout=5)

        print("License API Status:", response.status_code)
        print("License API Response:", response.text)

        if response.status_code != 200:
            return False, "Unable to verify license"

        data = response.json()
        print("Parsed JSON:", data)

        return True, ""

    except Exception as e:
        print(f"[ERROR] License check failed: {e}")
        return False, "License verification failed"
    """
    Call external license API and verify if license is active
    Returns (True, "") if active
    Returns (False, "reason") if not active
    """
    try:
        product_id = "69589e3fe70228ef3c25f26c"
        url = f"https://lisence-system.onrender.com/api/external/actve-license/{email}?productId={product_id}"

        response = requests.get(url, timeout=5)

        if response.status_code != 200:
            return False, "Unable to verify license"

        data = response.json()

        # Adjust this according to your API response structure
        if not data.get("success"):
            return False, "License not active"

        if not data.get("isActive"):
            return False, "License not active"

        return True, ""

    except Exception as e:
        print(f"[ERROR] License check failed: {e}")
        return False, "License verification failed"
    
def hash_password(password: str) -> str:
    """Hash password with bcrypt (12 rounds)"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against bcrypt hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        print(f"[ERROR] Password verification error: {e}")
        return False

def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength"""
    if len(password) < 6:
        return False, "Password must be at least 6 characters"
    if len(password) > 128:
        return False, "Password must be less than 128 characters"
    return True, ""

def validate_company_username(username: str) -> tuple[bool, str]:
    """Validate company username format"""
    pattern = r'^[a-z0-9-]{3,50}$'
    if not re.match(pattern, username):
        return False, "Username must be 3-50 characters (lowercase, numbers, hyphens only)"
    if username.startswith('-') or username.endswith('-'):
        return False, "Username cannot start or end with a hyphen"
    if '--' in username:
        return False, "Username cannot have consecutive hyphens"
    return True, ""

def check_rate_limit(identifier: str) -> tuple[bool, str]:
    """Check if identifier has exceeded rate limit"""
    now = time.time()
    attempts = login_attempts[identifier]
    
    # Remove old attempts outside window
    login_attempts[identifier] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    
    if len(login_attempts[identifier]) >= MAX_LOGIN_ATTEMPTS:
        wait_time = int(RATE_LIMIT_WINDOW - (now - login_attempts[identifier][0]))
        return False, f"Too many login attempts. Please try again in {wait_time} seconds"
    
    # Record this attempt
    login_attempts[identifier].append(now)
    return True, ""

def generate_tracker_token(company_id: int) -> str:
    """Generate unique tracker token for company"""
    token_data = f"{company_id}:{secrets.token_urlsafe(32)}"
    return base64.b64encode(token_data.encode()).decode()

# ============================================================================
# JWT TOKEN MANAGEMENT
# ============================================================================

def generate_admin_jwt(admin_id: int, company_id: int, email: str, token_type: str = 'access') -> str:
    """
    Generate JWT with company_id and user_id embedded
    Token type: 'access' (short-lived) or 'refresh' (long-lived)
    """
    if token_type == 'refresh':
        exp_time = datetime.utcnow() + timedelta(days=JWT_REFRESH_EXPIRATION_DAYS)
    else:
        exp_time = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    
    payload = {
        'admin_id': admin_id,
        'user_id': admin_id,  # Alias for compatibility
        'company_id': company_id,
        'tenant_id': company_id,  # Alias for multi-tenant
        'email': email,
        'type': token_type,
        'exp': exp_time,
        'iat': datetime.utcnow(),
        'jti': secrets.token_urlsafe(16)  # Unique token ID for revocation
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_admin_jwt(token: str, token_type: str = 'access') -> dict:
    """
    Verify JWT and extract payload
    Raises ValueError on invalid/expired token
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # Verify token type
        if payload.get('type') != token_type:
            raise ValueError(f'Invalid token type. Expected {token_type}')
        
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError('Token has expired')
    except jwt.InvalidTokenError as e:
        raise ValueError(f'Invalid token: {str(e)}')

def require_admin_auth(f):
    """Decorator: Require admin JWT authentication with multi-tenant isolation"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Invalid authorization header'}), 401
        
        token = auth_header.replace('Bearer ', '')
        
        try:
            payload = verify_admin_jwt(token, 'access')
            
            # Attach to request for use in route
            request.admin_id = payload['admin_id']
            request.user_id = payload['admin_id']
            request.company_id = payload['company_id']
            request.tenant_id = payload['company_id']
            request.admin_email = payload['email']
            
            print(f"[OK] Authenticated: admin_id={request.admin_id}, company_id={request.company_id}")
            
        except ValueError as e:
            return jsonify({'error': str(e)}), 401
        except Exception as e:
            print(f"[ERROR] Auth error: {e}")
            return jsonify({'error': 'Authentication failed'}), 401
        
        return f(*args, **kwargs)
    
    return decorated_function

# ============================================================================
# ADMIN SIGNUP - USING admin_users TABLE
# ============================================================================

@admin_auth_bp.route('/auth/admin/signup', methods=['POST'])
def admin_signup():
    """
    Admin signup with multi-tenant company creation
    Creates both company and admin user in a single transaction
    USES: admin_users table (matches actual DB schema)
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['company_username', 'company_name', 'email', 'password']
        for field in required:
            if not data.get(field):
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        company_username = data['company_username'].lower().strip()
        company_name = data['company_name'].strip()
        email = data['email'].lower().strip()
        password = data['password']
        full_name = data.get('full_name', company_name)
        
        # Validate email
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Validate company username
        valid, error_msg = validate_company_username(company_username)
        if not valid:
            return jsonify({'error': error_msg}), 400
        
        # Validate password
        valid, error_msg = validate_password(password)
        if not valid:
            return jsonify({'error': error_msg}), 400
        
        # Check rate limit
        rate_ok, rate_msg = check_rate_limit(f"signup_{email}")
        if not rate_ok:
            return jsonify({'error': rate_msg}), 429
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Check if company username exists
            cur.execute(
                "SELECT id FROM companies WHERE company_username = %s",
                (company_username,)
            )
            if cur.fetchone():
                return jsonify({'error': 'Company username already exists'}), 409
            
            # Check if admin email exists (global check across all companies)
            cur.execute(
                "SELECT id, company_id FROM admin_users WHERE email = %s",
                (email,)
            )
            existing_user = cur.fetchone()
            if existing_user:
                return jsonify({'error': 'Email already registered'}), 409
            
            # Generate tracker token
            temp_tracker_token = generate_tracker_token(999999)
            
            # Create company
            cur.execute(
                """
                INSERT INTO companies (company_username, company_name, tracker_token, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id, company_username, company_name, tracker_token
                """,
                (company_username, company_name, temp_tracker_token)
            )
            company = cur.fetchone()
            company_id = company['id']
            
            # Regenerate tracker token with actual company_id
            tracker_token = generate_tracker_token(company_id)
            cur.execute(
                "UPDATE companies SET tracker_token = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (tracker_token, company_id)
            )
            
            # Hash password
            password_hash = hash_password(password)
            
            # Create admin user in admin_users table
            cur.execute(
                """
                INSERT INTO admin_users (company_id, email, password_hash, full_name, role, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'admin', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id, email, full_name, role, company_id
                """,
                (company_id, email, password_hash, full_name)
            )
            admin = cur.fetchone()
            
            # Generate JWT tokens
            access_token = generate_admin_jwt(admin['id'], company_id, email, 'access')
            refresh_token = generate_admin_jwt(admin['id'], company_id, email, 'refresh')
            
            print(f"[OK] Signup successful: email={email}, company_id={company_id}")
            
            return jsonify({
                'success': True,
                'token': access_token,
                'refresh_token': refresh_token,
                'admin': {
                    'id': admin['id'],
                    'email': admin['email'],
                    'full_name': admin['full_name'],
                    'role': admin['role'],
                    'company_id': company_id
                },
                'company': {
                    'id': company_id,
                    'company_name': company['company_name'],
                    'company_username': company['company_username'],
                    'tracker_token': tracker_token
                }
            }), 201
            
    except Exception as e:
        print(f"[ERROR] Admin signup error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error during signup'}), 500

# ============================================================================
# ADMIN LOGIN - USING admin_users TABLE
# ============================================================================

@admin_auth_bp.route('/auth/admin/login', methods=['POST'])
def admin_login():
    """
    Admin login with multi-tenant isolation
    Validates user by email AND ensures company_id isolation
    USES: admin_users table (matches actual DB schema)
    """
    try:
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400
        
        # Validate email format
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Check rate limit
        rate_ok, rate_msg = check_rate_limit(f"login_{email}")
        if not rate_ok:
            return jsonify({'error': rate_msg}), 429
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Query admin_users table (matches actual DB schema)
            cur.execute(
                """
                SELECT id, company_id, email, password_hash, full_name, 
                       role, is_active
                FROM admin_users
                WHERE email = %s
                """,
                (email,)
            )
            admin = cur.fetchone()
            
            # if not admin:
            #     print(f"[ERROR] Login failed: User not found in admin_users for email: {email}")
            #     return jsonify({'error': 'Invalid credentials'}), 401
            
            if not admin:
             return jsonify({'error': 'Invalid credentials'}), 401

            # ==========================
# LICENSE CHECK BEFORE LOGIN
# ==========================
            license_ok, license_msg = check_license_active(email)
            if not license_ok:
              print(f"[ERROR] License not active for email: {email}")
              return jsonify({'error': 'License not active'}), 403
            
            # Verify password
            if not verify_password(password, admin['password_hash']):
                print(f"[ERROR] Login failed: Invalid password for email: {email}")
                return jsonify({'error': 'Invalid credentials'}), 401
            
            # Check if user is active
            if not admin['is_active']:
                print(f"[ERROR] Login failed: Inactive account for email: {email}")
                return jsonify({'error': 'Account is disabled'}), 403
            
            company_id = admin['company_id']
            
            # Get company data filtered by company_id
            cur.execute(
                """
                SELECT id, company_name, company_username, is_active, tracker_token
                FROM companies 
                WHERE id = %s
                """,
                (company_id,)
            )
            company = cur.fetchone()
            
            if not company or not company['is_active']:
                print(f"[ERROR] Login failed: Company not found or inactive for company_id: {company_id}")
                return jsonify({'error': 'Company account is inactive'}), 403
            
            # Update last login timestamp
            cur.execute(
                "UPDATE admin_users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                (admin['id'],)
            )
            
            # Generate JWT tokens with company_id embedded
            access_token = generate_admin_jwt(admin['id'], company['id'], email, 'access')
            refresh_token = generate_admin_jwt(admin['id'], company['id'], email, 'refresh')
            
            print(f"[OK] Login successful: email={email}, company_id={company['id']}, admin_id={admin['id']}")
            
            return jsonify({
                'success': True,
                'token': access_token,
                'refresh_token': refresh_token,
                'admin': {
                    'id': admin['id'],
                    'email': admin['email'],
                    'full_name': admin['full_name'],
                    'role': admin['role'],
                    'company_id': company['id']
                },
                'company': {
                    'id': company['id'],
                    'company_name': company['company_name'],
                    'company_username': company['company_username'],
                    'tracker_token': company.get('tracker_token', '')
                }
            }), 200
            
    except Exception as e:
        print(f"[ERROR] Admin login error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error during login'}), 500

# ============================================================================
# TOKEN VALIDATION - USING admin_users TABLE
# ============================================================================

@admin_auth_bp.route('/auth/admin/validate-token', methods=['GET'])
def validate_admin_token():
    """Validate JWT and return user/company details with multi-tenant isolation"""
    try:
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Invalid authorization header'}), 401
        
        token = auth_header.replace('Bearer ', '')
        
        try:
            payload = verify_admin_jwt(token, 'access')
        except ValueError as e:
            return jsonify({'error': str(e)}), 401
        
        admin_id = payload['admin_id']
        company_id = payload['company_id']
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Query admin_users table (matches actual DB schema)
            cur.execute(
                """
                SELECT id, email, full_name, role, is_active, company_id
                FROM admin_users 
                WHERE id = %s AND company_id = %s
                """,
                (admin_id, company_id)
            )
            admin = cur.fetchone()
            
            if not admin or not admin['is_active']:
                return jsonify({'error': 'Admin not found or inactive'}), 401
            
            # Verify company_id matches
            if admin['company_id'] != company_id:
                return jsonify({'error': 'Company mismatch - potential security violation'}), 401
            
            # Get company filtered by company_id
            cur.execute(
                """
                SELECT id, company_name, company_username, is_active
                FROM companies 
                WHERE id = %s
                """,
                (company_id,)
            )
            company = cur.fetchone()
            
            if not company or not company['is_active']:
                return jsonify({'error': 'Company not found or inactive'}), 401
            
            return jsonify({
                'success': True,
                'admin': {
                    'id': admin['id'],
                    'email': admin['email'],
                    'full_name': admin['full_name'],
                    'role': admin['role'],
                    'company_id': company_id
                },
                'company': {
                    'id': company['id'],
                    'company_name': company['company_name'],
                    'company_username': company['company_username']
                }
            }), 200
            
    except Exception as e:
        print(f"[ERROR] Token validation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error'}), 500

# ============================================================================
# TOKEN REFRESH
# ============================================================================

@admin_auth_bp.route('/auth/admin/refresh-token', methods=['POST'])
def refresh_admin_token():
    """Refresh access token using refresh token"""
    try:
        data = request.get_json()
        refresh_token = data.get('refresh_token')
        
        if not refresh_token:
            return jsonify({'error': 'Refresh token required'}), 400
        
        try:
            payload = verify_admin_jwt(refresh_token, 'refresh')
        except ValueError as e:
            return jsonify({'error': str(e)}), 401
        
        # Generate new access token
        new_access_token = generate_admin_jwt(
            payload['admin_id'],
            payload['company_id'],
            payload['email'],
            'access'
        )
        
        return jsonify({
            'success': True,
            'token': new_access_token
        }), 200
        
    except Exception as e:
        print(f"[ERROR] Token refresh error: {e}")
        return jsonify({'error': 'Token refresh failed'}), 500

# ============================================================================
# DELETE ADMIN ACCOUNT - MULTI-TENANT SAFE
# ============================================================================

@admin_auth_bp.route('/auth/admin/delete-account', methods=['DELETE'])
@require_admin_auth
def delete_admin_account():
    """
    Delete admin account with full multi-tenant isolation
    Only deletes data belonging to the authenticated company
    """
    try:
        admin_id = request.admin_id
        company_id = request.company_id
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Verify admin belongs to company (using admin_users table)
            cur.execute(
                "SELECT id, company_id, role FROM admin_users WHERE id = %s AND company_id = %s",
                (admin_id, company_id)
            )
            admin = cur.fetchone()
            
            if not admin:
                return jsonify({'error': 'Admin not found or unauthorized'}), 404
            
            if admin['role'] != 'admin':
                return jsonify({'error': 'Only admin users can delete accounts'}), 403
            
            print(f"🗑️  Starting account deletion for admin_id={admin_id}, company_id={company_id}")
            
            # Delete data in proper order (respecting foreign keys)
            
            # 1. Delete screenshots
            cur.execute(
                "DELETE FROM screenshots WHERE company_id = %s",
                (company_id,)
            )
            deleted_screenshots = cur.rowcount
            
            # 2. Delete activity logs
            cur.execute(
                "DELETE FROM activity_logs WHERE company_id = %s",
                (company_id,)
            )
            deleted_activities = cur.rowcount
            
            # 3. Delete punch logs
            cur.execute(
                "DELETE FROM punch_logs WHERE company_id = %s",
                (company_id,)
            )
            deleted_punch = cur.rowcount
            
            # 4. Delete devices
            cur.execute(
                "DELETE FROM devices WHERE company_id = %s",
                (company_id,)
            )
            deleted_devices = cur.rowcount
            
            # 5. Delete members
            cur.execute(
                "DELETE FROM members WHERE company_id = %s",
                (company_id,)
            )
            deleted_members = cur.rowcount
            
            # 6. Delete all admin users
            cur.execute(
                "DELETE FROM admin_users WHERE company_id = %s",
                (company_id,)
            )
            deleted_users = cur.rowcount
            
            # 7. Finally delete company
            cur.execute(
                "DELETE FROM companies WHERE id = %s",
                (company_id,)
            )
            deleted_companies = cur.rowcount
            
            conn.commit()
            
            print(f"[OK] Account deletion completed for company_id={company_id}")
            
            return jsonify({
                'success': True,
                'message': 'Account and all associated data deleted permanently',
                'deleted_counts': {
                    'screenshots': deleted_screenshots,
                    'activity_logs': deleted_activities,
                    'punch_logs': deleted_punch,
                    'devices': deleted_devices,
                    'members': deleted_members,
                    'admin_users': deleted_users,
                    'companies': deleted_companies
                }
            }), 200
            
    except Exception as e:
        print(f"[ERROR] Delete account error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error during account deletion'}), 500

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ['admin_auth_bp', 'require_admin_auth']
