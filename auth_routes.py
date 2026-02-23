"""
AUTH_ROUTES.PY - Authentication Routes (Synchronous + psycopg2)
================================================================
✅ psycopg2 ONLY (no SQLAlchemy, no async)
✅ JWT token-based authentication
✅ Multi-tenant company creation
✅ Synchronous route handlers
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from functools import wraps
import bcrypt
import jwt
import os

from db import get_db

# ============================================================================
# BLUEPRINT SETUP
# ============================================================================

auth_bp = Blueprint('auth', __name__)

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-super-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24 * 30  # 30 days

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def generate_token(user_id: int, company_id: int, email: str) -> str:
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'company_id': company_id,
        'email': email,
        # 'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        # 'iat': datetime.utcnow()
          'exp': datetime.now(IST)
          'iat': datetime.now(IST)

    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError('Token has expired')
    except jwt.InvalidTokenError:
        raise ValueError('Invalid token')


def validate_username(username: str) -> bool:
    """Validate company username format"""
    import re
    pattern = r'^[a-z0-9-]{3,50}$'
    return bool(re.match(pattern, username))


def require_auth(f):
    """Decorator to require JWT authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Invalid authorization header'}), 401
        
        token = auth_header.replace('Bearer ', '')
        
        try:
            payload = verify_token(token)
            request.user_id = payload['user_id']
            request.company_id = payload['company_id']
            request.user_email = payload['email']
        except ValueError as e:
            return jsonify({'error': str(e)}), 401
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# ROUTE: SIGNUP
# ============================================================================

@auth_bp.route('/auth/signup', methods=['POST'])
def signup():
    """
    Create a new company account (multi-tenant signup)
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['company_username', 'company_name', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        company_username = data['company_username'].lower().strip()
        company_name = data['company_name'].strip()
        email = data['email'].lower().strip()
        password = data['password']
        full_name = data.get('full_name', company_name)
        
        # Validate username format
        if not validate_username(company_username):
            return jsonify({
                'success': False,
                'error': 'Invalid company username format. Use lowercase letters, numbers, and hyphens only (3-50 chars)'
            }), 400
        
        # Validate password length
        if len(password) < 6:
            return jsonify({
                'success': False,
                'error': 'Password must be at least 6 characters long'
            }), 400
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Check if company username already exists
            # Try both column names for compatibility
            try:
                cur.execute(
                    "SELECT id FROM companies WHERE company_username = %s",
                    (company_username,)
                )
            except:
                cur.execute(
                    "SELECT id FROM companies WHERE username = %s",
                    (company_username,)
                )
            
            if cur.fetchone():
                return jsonify({
                    'success': False,
                    'error': 'Company username already exists'
                }), 409
            
            # Check if email already exists in admin_users only
            cur.execute(
                "SELECT id FROM admin_users WHERE email = %s",
                (email,)
            )
            if cur.fetchone():
                return jsonify({
                    'success': False,
                    'error': 'Email already registered'
                }), 409
            
            # Create new company - try both column name schemas
            try:
                cur.execute(
                    """
                    INSERT INTO companies (company_username, company_name, is_active)
                    VALUES (%s, %s, TRUE)
                    RETURNING id, company_username, company_name
                    """,
                    (company_username, company_name)
                )
            except:
                cur.execute(
                    """
                    INSERT INTO companies (username, name, is_active)
                    VALUES (%s, %s, TRUE)
                    RETURNING id, username as company_username, name as company_name
                    """,
                    (company_username, company_name)
                )
            company = cur.fetchone()
            
            # Hash password
            password_hash = hash_password(password)
            
            # Create admin user in admin_users table only
            cur.execute(
                """
                INSERT INTO admin_users (company_id, email, password_hash, full_name, role, is_active)
                VALUES (%s, %s, %s, %s, 'admin', TRUE)
                RETURNING id, email, full_name, role, company_id
                """,
                (company['id'], email, password_hash, full_name)
            )
            admin = cur.fetchone()
            
            # COMMIT the transaction to save to database
            conn.commit()
            
            print(f"[OK] Signup successful - Company: {company['id']}, Admin: {admin['id']}")
            
            # Generate JWT token
            token = generate_token(admin['id'], company['id'], email)
            
            return jsonify({
                'success': True,
                'token': token,
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
                    'company_username': company['company_username']
                }
            }), 201
    
    except Exception as e:
        print(f"[ERROR] Signup error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error during signup'
        }), 500


# ============================================================================
# ROUTE: LOGIN
# ============================================================================

@auth_bp.route('/auth/login', methods=['POST'])
def login():
    """
    Login to existing account
    """
    try:
        data = request.get_json()
        
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email and password are required'
            }), 400
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Find user by email in admin_users table only
            cur.execute(
                "SELECT id, company_id, email, password_hash, full_name, role, is_active FROM admin_users WHERE email = %s",
                (email,)
            )
            admin = cur.fetchone()
            
            if not admin:
                return jsonify({
                    'success': False,
                    'error': 'Invalid credentials'
                }), 401
            
            # Verify password
            if not verify_password(password, admin['password_hash']):
                return jsonify({
                    'success': False,
                    'error': 'Invalid credentials'
                }), 401
            
            # Check if user is active
            if not admin['is_active']:
                return jsonify({
                    'success': False,
                    'error': 'Account is disabled'
                }), 403
            
            # Get company details - handle both column name schemas
            try:
                cur.execute(
                    "SELECT id, company_name, company_username, is_active FROM companies WHERE id = %s",
                    (admin['company_id'],)
                )
            except:
                cur.execute(
                    "SELECT id, name as company_name, username as company_username, is_active FROM companies WHERE id = %s",
                    (admin['company_id'],)
                )
            company = cur.fetchone()
            
            if not company or not company['is_active']:
                return jsonify({
                    'success': False,
                    'error': 'Company account is inactive'
                }), 403
            
            # Update last login in admin_users table
            cur.execute(
                "UPDATE admin_users SET last_login = %s WHERE id = %s",
                (datetime.utcnow(), admin['id'])
            )
            
            # COMMIT the transaction
            conn.commit()
            
            print(f"[OK] Login successful - Admin: {admin['id']}, Company: {company['id']}")
            
            # Generate JWT token
            token = generate_token(admin['id'], company['id'], email)
            
            return jsonify({
                'success': True,
                'token': token,
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
                    'company_username': company['company_username']
                }
            }), 200
    
    except Exception as e:
        print(f"[ERROR] Login error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error during login'
        }), 500


# ============================================================================
# ROUTE: VALIDATE TOKEN
# ============================================================================

@auth_bp.route('/auth/validate-token', methods=['GET'])
def validate_token_route():
    """
    Validate JWT token and return user details
    """
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'error': 'Invalid authorization header'
            }), 401
        
        token = auth_header.replace('Bearer ', '')
        
        try:
            payload = verify_token(token)
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 401
        
        user_id = payload['user_id']
        company_id = payload['company_id']
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Get admin user from admin_users table only
            cur.execute(
                "SELECT id, email, full_name, role, is_active FROM admin_users WHERE id = %s",
                (user_id,)
            )
            admin = cur.fetchone()
            
            if not admin or not admin['is_active']:
                return jsonify({
                    'success': False,
                    'error': 'User not found or inactive'
                }), 401
            
            # Get company - handle both column name schemas
            try:
                cur.execute(
                    "SELECT id, company_name, company_username, is_active FROM companies WHERE id = %s",
                    (company_id,)
                )
            except:
                cur.execute(
                    "SELECT id, name as company_name, username as company_username, is_active FROM companies WHERE id = %s",
                    (company_id,)
                )
            company = cur.fetchone()
            
            if not company or not company['is_active']:
                return jsonify({
                    'success': False,
                    'error': 'Company not found or inactive'
                }), 401
            
            return jsonify({
                'success': True,
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
                    'company_username': company['company_username']
                }
            }), 200
    
    except Exception as e:
        print(f"[ERROR] Token validation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ['auth_bp', 'verify_token', 'require_auth']
