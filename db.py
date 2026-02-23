"""
DB.PY - PostgreSQL Database Connection for WorkEye
===================================================
[OK] Uses external Render PostgreSQL database
[OK] Proper SSL connection configuration
[OK] Connection pooling with psycopg2
[OK] IST (Indian Standard Time) timezone support
[OK] Compatible with all backend routes
[OK] FIXED: Complete external database URL with full hostname
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from contextlib import contextmanager
from datetime import datetime
import pytz

# ============================================================================
# TIMEZONE CONFIGURATION
# ============================================================================

IST = pytz.timezone('Asia/Kolkata')

def get_ist_now():
    """Get current time in IST"""
    return datetime.now(IST)

def convert_to_ist(utc_dt):
    """Convert UTC datetime to IST"""
    if utc_dt is None:
        return None
    if utc_dt.tzinfo is None:
        utc_dt = pytz.UTC.localize(utc_dt)
    return utc_dt.astimezone(IST)

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# HARDCODED EXTERNAL DATABASE URL - This ensures we ALWAYS have a valid connection
EXTERNAL_DB_URL = 'postgresql://work_eye_db_user:DeXsKDcQNO6rpdQypAjDECEjqRXVa8hr@dpg-d52ij3ali9vc73f8tn40-a.singapore-postgres.render.com/work_eye_db'

# Use the external PostgreSQL database URL with COMPLETE hostname
# Priority: INTERNAL_DATABASE_URL > DATABASE_URL > Hardcoded fallback
DATABASE_URL = os.environ.get(
    'INTERNAL_DATABASE_URL',
    os.environ.get(
        'DATABASE_URL',
        EXTERNAL_DB_URL
    )
)

print(f"[DB DEBUG] Environment DATABASE_URL exists: {bool(os.environ.get('DATABASE_URL'))}")
print(f"[DB DEBUG] Environment INTERNAL_DATABASE_URL exists: {bool(os.environ.get('INTERNAL_DATABASE_URL'))}")
print(f"[DB DEBUG] Using DATABASE_URL: {DATABASE_URL[:60] if DATABASE_URL else 'NONE'}...")

# Render uses postgres://, PostgreSQL requires postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    print(f"[DB CONVERT] Converted postgres:// to postgresql://")

# Log connection info (hide password)
if '@' in DATABASE_URL:
    connection_info = DATABASE_URL.split('@')[1].split('/')[0]
    print(f"[DB LINK] Connecting to: {connection_info}")
else:
    print(f"[DB LINK] Connecting to: database")

# ============================================================================
# CONNECTION POOL (for better performance)
# ============================================================================

connection_pool = None

def initialize_connection_pool():
    """Initialize the connection pool with SSL required"""
    global connection_pool
    
    # Debug: Print what we're trying to connect to
    print(f"[DB DEBUG] DATABASE_URL length: {len(DATABASE_URL)}")
    print(f"[DB DEBUG] DATABASE_URL starts with: {DATABASE_URL[:50] if len(DATABASE_URL) > 50 else DATABASE_URL}")
    
    # Verify DATABASE_URL is set
    if not DATABASE_URL or 'postgresql://' not in DATABASE_URL:
        print(f"[DB ERROR] CRITICAL: DATABASE_URL is not properly set!")
        print(f"[DB ERROR] DATABASE_URL value: {DATABASE_URL}")
        return False
    
    try:
        print(f"[DB INIT] Initializing connection pool...")
        
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1,  # minimum connections
            20,  # maximum connections
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            sslmode='require',  # Required for Render PostgreSQL
            connect_timeout=10  # 10 second timeout
        )
        print("[DB OK] Database connection pool initialized successfully")
        return True
    except Exception as e:
        print(f"[DB ERROR] Failed to create connection pool: {e}")
        print(f"[DB ERROR] Attempting direct connection test...")
        try:
            # Try direct connection to verify
            test_conn = psycopg2.connect(
                DATABASE_URL,
                sslmode='require',
                connect_timeout=10
            )
            test_conn.close()
            print("[DB OK] Direct connection test succeeded!")
            # Try pool again
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 20, DATABASE_URL,
                cursor_factory=RealDictCursor,
                sslmode='require',
                connect_timeout=10
            )
            print("[DB OK] Pool created on second attempt")
            return True
        except Exception as e2:
            print(f"[DB ERROR] Direct connection also failed: {e2}")
            import traceback
            traceback.print_exc()
            return False






# def initialize_connection_pool():
#     global connection_pool

#     try:
#         print("📡 Initializing connection pool...")

#         connection_pool = psycopg2.pool.SimpleConnectionPool(
#             1,
#             20,
#             dsn=DATABASE_URL,          # ✅ use dsn=
#             cursor_factory=RealDictCursor,
#             sslmode="require"
#         )

#         print("✅ Database connection pool initialized successfully")
#         return True

#     except Exception as e:
#         print(f"❌ Failed to create connection pool: {e}")

#         try:
#             print("🔄 Trying direct connection test...")
#             test_conn = psycopg2.connect(
#                 dsn=DATABASE_URL,
#                 cursor_factory=RealDictCursor,
#                 sslmode="require"
#             )
#             test_conn.close()
#             print("✅ Direct connection successful")
#             return True
#         except Exception as e2:
#             print(f"❌ Direct connection also failed: {e2}")
#             return False
# ============================================================================
# CONNECTION MANAGEMENT
# ============================================================================

def get_db_connection():
    """
    Get a database connection from the pool.
    If pool doesn't exist, create a direct connection.
    
    Usage:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users")
            result = cur.fetchall()
        finally:
            conn.close()
    """
    global connection_pool
    
    if connection_pool is None:
        # Fallback: create direct connection
        return psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            sslmode='require',
            connect_timeout=10
        )
    
    try:
        return connection_pool.getconn()
    except:
        # Fallback: create direct connection
        return psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            sslmode='require',
            connect_timeout=10
        )


def return_connection(conn):
    """Return a connection to the pool"""
    global connection_pool
    if connection_pool is not None:
        try:
            connection_pool.putconn(conn)
        except:
            conn.close()
    else:
        conn.close()


@contextmanager
def get_db():
    """
    Context manager for database connections.
    Auto-commits on success, rolls back on error.
    
    Usage:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO users ...")
            # Auto-commit on exit
    """
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        return_connection(conn)


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db():
    """
    Initialize database tables if they don't exist.
    This is safe to run multiple times - it only creates missing tables.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("[DB CHECK] Checking database schema...")
        
        # Check if companies table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'companies'
            )
        """)
        companies_exists = cur.fetchone()['exists']
        
        if not companies_exists:
            print("[DB WARN] Database tables not found. Please run init_db.py first.")
            conn.close()
            return False
        
        # Check companies table structure
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'companies'
            ORDER BY ordinal_position
        """)
        company_columns = [row['column_name'] for row in cur.fetchall()]
        print(f"[DB OK] Companies table columns: {', '.join(company_columns)}")
        
        # Check admin_users table
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'admin_users'
            )
        """)
        admin_users_exists = cur.fetchone()['exists']
        
        if admin_users_exists:
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'admin_users'
                ORDER BY ordinal_position
            """)
            admin_columns = [row['column_name'] for row in cur.fetchall()]
            print(f"[DB OK] Admin_users table columns: {', '.join(admin_columns)}")
        else:
            print("[DB WARN] admin_users table not found - admin login may not work")
        
        # Check members table
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'members'
            )
        """)
        members_exists = cur.fetchone()['exists']
        
        if members_exists:
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'members'
                ORDER BY ordinal_position
            """)
            member_columns = [row['column_name'] for row in cur.fetchall()]
            print(f"[DB OK] Members table columns: {', '.join(member_columns)}")
        
        # List all tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        all_tables = [row['table_name'] for row in cur.fetchall()]
        print(f"[DB TABLES] Database tables ({len(all_tables)}): {', '.join(all_tables[:10])}{'...' if len(all_tables) > 10 else ''}")
        
        conn.commit()
        print("[DB OK] Database schema verified")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR] Database initialization error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cur.close()
        return_connection(conn)


# ============================================================================
# DATABASE HEALTH CHECK
# ============================================================================

def check_db_health():
    """
    Check if database connection is healthy.
    Returns True if connection is working, False otherwise.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 as health_check")
        result = cur.fetchone()
        cur.close()
        return_connection(conn)
        
        if result and result['health_check'] == 1:
            return True
        return False
    except Exception as e:
        print(f"[DB ERROR] Database health check failed: {e}")
        return False


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def execute_query(query, params=None):
    """
    Execute a query and return results.
    
    Args:
        query: SQL query string
        params: Query parameters tuple or dict
    
    Returns:
        Query results as list of dicts
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, params or ())
        try:
            return cur.fetchall()
        except psycopg2.ProgrammingError:
            # No results to fetch (INSERT/UPDATE/DELETE)
            return None


def fetch_one(query, params=None):
    """
    Fetch a single row from database.
    
    Returns:
        Single row as dict or None
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, params or ())
        return cur.fetchone()


def fetch_all(query, params=None):
    """
    Fetch all rows from database.
    
    Returns:
        List of dicts
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, params or ())
        return cur.fetchall()


# ============================================================================
# INITIALIZATION ON MODULE LOAD
# ============================================================================

# Initialize connection pool when module is imported
print("[DB INIT] Initializing database connection...")
if initialize_connection_pool():
    print("[DB OK] Database ready!")
    # Verify schema
    init_db()
else:
    print("[DB WARN] Database connection pool failed, will use direct connections")

# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'get_db_connection',
    'return_connection',
    'get_db',
    'init_db',
    'check_db_health',
    'execute_query',
    'fetch_one',
    'fetch_all',
    'IST',
    'get_ist_now',
    'convert_to_ist'
]
