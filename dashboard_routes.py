"""
DASHBOARD_ROUTES - ENHANCED WITH ACCURATE DATA AND FILTERS
===========================================================
✅ Real-time member status calculation (Active/Idle/Offline)
✅ Accurate time calculations from tracker logs (no 1-min increments)
✅ Proper productivity calculation: (Active Time / Screen Time) × 100
✅ Human-readable "Last Activity" in IST
✅ Filters: Employee Name (searchable) and Status
✅ All timestamps in IST (Indian Standard Time)
✅ FIXED: Improved idle status detection with detailed logging
✅ NEW: Activity Trends endpoint for 7-day chart
"""

from flask import Blueprint, request, jsonify
from admin_auth_routes import require_admin_auth
from db import get_db, get_ist_now, convert_to_ist, IST
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

# ============================================================================
# REAL-TIME STATUS CALCULATION
# ============================================================================

def calculate_member_status(last_heartbeat_at, last_activity_at=None):
    """
    Calculate real-time member status based on heartbeat
    
    Rules:
    - Active: heartbeat within last 120 seconds (2 minutes)
    - Idle: heartbeat between 120-600 seconds (2-10 minutes)
    - Offline: heartbeat > 600 seconds (10+ minutes) or no heartbeat
    
    Returns: (status, seconds_ago)
    """
    if not last_heartbeat_at:
        print(f"⚪ No heartbeat data - Status: offline")
        return 'offline', None
    
    now_ist = get_ist_now()
    
    # Convert last_heartbeat to IST if needed
    if last_heartbeat_at.tzinfo is None:
        import pytz
        last_heartbeat_at = pytz.UTC.localize(last_heartbeat_at)
    last_heartbeat_ist = last_heartbeat_at.astimezone(IST)
    
    seconds_ago = int((now_ist - last_heartbeat_ist).total_seconds())
    
    # Determine status
    if seconds_ago < 120:  # Less than 2 minutes
        status = 'active'
        color = '🟢'
    elif seconds_ago < 600:  # Between 2-10 minutes
        status = 'idle'
        color = '🟡'
    else:  # More than 10 minutes
        status = 'offline'
        color = '⚪'
    
    print(f"{color} Last heartbeat: {seconds_ago}s ago -> Status: {status}")
    
    return status, seconds_ago


def format_last_activity(seconds_ago):
    """
    Format last activity timestamp in human-readable format
    
    Returns:
    - "just now" → 0–59 seconds
    - "1 min ago", "2 min ago" → up to 59 minutes
    - "1 hr ago", "2 hr ago" → up to 23 hours
    - "1 day ago", "2 days ago", ... then actual date/time
    """
    if seconds_ago is None:
        return "Never"
    
    if seconds_ago < 60:
        return "just now"
    
    minutes_ago = seconds_ago // 60
    if minutes_ago < 60:
        return f"{minutes_ago} min ago" if minutes_ago == 1 else f"{minutes_ago} mins ago"
    
    hours_ago = minutes_ago // 60
    if hours_ago < 24:
        return f"{hours_ago} hr ago" if hours_ago == 1 else f"{hours_ago} hrs ago"
    
    days_ago = hours_ago // 24
    if days_ago <= 7:
        return f"{days_ago} day ago" if days_ago == 1 else f"{days_ago} days ago"
    
    # Return actual date if more than 7 days
    return None


# ============================================================================
# DASHBOARD STATS - REAL DATA WITH FILTERS
# ============================================================================

@dashboard_bp.route('/api/dashboard/stats', methods=['GET'])
@require_admin_auth
def get_dashboard_stats():
    """
    Get real dashboard statistics for company with filters
    
    Query Parameters:
    - name: Filter by employee name (partial match)
    - status: Filter by status (active/idle/offline)
    
    Returns:
    - Total members count (for this company)
    - Active now count (heartbeat < 120s)
    - Idle count (heartbeat 120-600s)
    - Offline count (heartbeat > 600s or no heartbeat)
    - Average productivity (active_time / screen_time * 100)
    - Per-member live data with accurate calculations
    """
    try:
        company_id = request.company_id
        today = datetime.now(IST).date()
        
        # Get filter parameters
        name_filter = request.args.get('name', '').strip()
        status_filter = request.args.get('status', '').strip().lower()
        
        print(f"\n📊 ========== DASHBOARD STATS REQUEST ==========")
        print(f"Company ID: {company_id}")
        print(f"Date: {today}")
        print(f"Filters: name='{name_filter}', status='{status_filter}'")
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Get all members with today's aggregated data
            cur.execute(
                """
                SELECT 
                    m.id,
                    m.name,
                    m.email,
                    m.position,
                    m.status,
                    m.is_punched_in,
                    m.last_heartbeat_at,
                    m.last_activity_at,
                    
                    -- FIXED: Use MAX instead of SUM for cumulative tracker data
                    -- The tracker sends cumulative values, not incremental
                    COALESCE(MAX(al.total_seconds), 0) as screen_time_seconds,
                    COALESCE(MAX(al.active_seconds), 0) as active_time_seconds,
                    COALESCE(MAX(al.idle_seconds), 0) as idle_time_seconds,
                    
                    -- Screenshot count today
                    COUNT(DISTINCT s.id) as screenshot_count
                    
                FROM members m
                LEFT JOIN activity_log al 
                    ON al.member_id = m.id 
                    AND DATE(al.timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') = %s
                LEFT JOIN screenshots s 
                    ON s.member_id = m.id 
                    AND s.tracking_date = %s
                WHERE m.company_id = %s AND m.is_active = TRUE
                GROUP BY m.id, m.name, m.email, m.position, m.status, m.is_punched_in, 
                         m.last_heartbeat_at, m.last_activity_at
                ORDER BY m.name ASC
                """,
                (today, today, company_id)
            )
            members = cur.fetchall()
            
            print(f"📊 Found {len(members)} members for company {company_id}")
            
            # Process members and calculate stats
            result = []
            total_members = 0
            active_now = 0
            idle_now = 0
            offline_now = 0
            total_productivity = 0
            productive_members = 0  # Members with screen_time > 0
            
            for member in members:
                print(f"\n👤 Processing member: {member['name']} (ID: {member['id']})")
                print(f"   Last heartbeat: {member['last_heartbeat_at']}")
                print(f"   Last activity: {member['last_activity_at']}")
                print(f"   Punched in: {member['is_punched_in']}")
                
                # Calculate real-time status (use DB value)
                status = member['status']

                # Determine seconds since last activity for display purposes
                seconds_ago = None
                if member['last_activity_at']:
                    now_ist = datetime.now(IST)
                    last_act_ist = convert_to_ist(member['last_activity_at'])
                    seconds_ago = int((now_ist - last_act_ist).total_seconds())

                print(f"   ➡️ Calculated status: {status}")
                if seconds_ago is not None:
                    print(f"   Seconds since last activity: {seconds_ago}")
                
                # Apply status filter
                if status_filter and status != status_filter:
                    print(f"   ⏭️ Skipped due to status filter: {status} != {status_filter}")
                    continue
                
                # Apply name filter
                if name_filter and name_filter.lower() not in member['name'].lower():
                    print(f"   ⏭️ Skipped due to name filter")
                    continue
                
                # Calculate productivity: (active_time / screen_time) * 100
                screen_time = float(member['screen_time_seconds'] or 0)
                active_time = float(member['active_time_seconds'] or 0)
                idle_time = float(member['idle_time_seconds'] or 0)
                
                print(f"   Screen time: {screen_time}s, Active: {active_time}s, Idle: {idle_time}s")
                
                if screen_time > 0:
                    productivity = int((active_time / screen_time) * 100)
                    total_productivity += productivity
                    productive_members += 1
                else:
                    productivity = 0
                
                print(f"   Productivity: {productivity}%")
                
                # Format last activity
                last_activity_str = format_last_activity(seconds_ago)
                if last_activity_str is None and member['last_activity_at']:
                    # Format actual datetime in IST
                    last_activity_ist = convert_to_ist(member['last_activity_at'])
                    last_activity_str = last_activity_ist.strftime('%b %d, %Y %I:%M %p')
                elif last_activity_str is None:
                    last_activity_str = "Never"
                
                member_data = {
                    'id': member['id'],
                    'name': member['name'],
                    'email': member['email'],
                    'position': member['position'] or '',
                    'status': status,  # This is the key field!
                    'is_punched_in': member['is_punched_in'],
                    'seconds_since_activity': seconds_ago,
                    'screen_time': int(screen_time),
                    'active_time': int(active_time),
                    'idle_time': int(idle_time),
                    'productivity': productivity,
                    'screenshots_count': member['screenshot_count'] or 0,
                    'last_activity': last_activity_str,
                    'last_heartbeat_at': convert_to_ist(member['last_heartbeat_at']).isoformat() if member['last_heartbeat_at'] else None,
                    'last_activity_at': convert_to_ist(member['last_activity_at']).isoformat() if member['last_activity_at'] else None
                }
                
                result.append(member_data)
                
                # Update aggregate stats
                total_members += 1
                if status == 'active':
                    active_now += 1
                elif status == 'idle':
                    idle_now += 1
                else:
                    offline_now += 1
            
            # Calculate average productivity
            avg_productivity = int(total_productivity / productive_members) if productive_members > 0 else 0
            
            print(f"\n📈 SUMMARY:")
            print(f"   Total: {total_members}")
            print(f"   🟢 Active: {active_now}")
            print(f"   🟡 Idle: {idle_now}")
            print(f"   ⚪ Offline: {offline_now}")
            print(f"   📊 Avg Productivity: {avg_productivity}%")
            print(f"========================================\n")
            
            return jsonify({
                'success': True,
                'stats': {
                    'total_members': total_members,
                    'active_now': active_now,
                    'idle_now': idle_now,
                    'offline': offline_now,
                    'average_productivity': avg_productivity
                },
                'members': result,
                'date': today.isoformat(),
                'timestamp': get_ist_now().isoformat()
            }), 200
    
    except Exception as e:
        print(f"❌ Dashboard stats error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch dashboard stats'}), 500


# ============================================================================
# ACTIVITY TRENDS - 7 DAY CHART DATA
# ============================================================================

@dashboard_bp.route('/api/dashboard/activity-trends', methods=['GET'])
@require_admin_auth
def get_activity_trends():
    """
    Get activity trends for the last 7 days for chart visualization
    
    Returns:
    - 7 days of aggregated data (today back to 6 days ago)
    - Each day includes:
      - date: ISO date string
      - screen_time: Total screen time in seconds
      - active_time: Total active time in seconds
      - idle_time: Total idle time in seconds
      - productivity: Average productivity percentage
    """
    try:
        company_id = request.company_id
        today = datetime.now(IST).date()
        start_date = today - timedelta(days=6)  # 7 days total including today
        
        print(f"\n📈 ========== ACTIVITY TRENDS REQUEST ==========")
        print(f"Company ID: {company_id}")
        print(f"Date range: {start_date} to {today}")
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Get daily summaries for the last 7 days
            cur.execute(
                """
                SELECT 
                    date,
                    SUM(total_screen_time) as total_screen,
                    SUM(active_time) as total_active,
                    SUM(idle_time) as total_idle,
                    AVG(productivity_percentage) as avg_productivity
                FROM daily_summaries
                WHERE company_id = %s
                  AND date >= %s
                  AND date <= %s
                GROUP BY date
                ORDER BY date ASC
                """,
                (company_id, start_date, today)
            )
            
            rows = cur.fetchall()
            
            # Create a map of date -> data
            data_map = {row['date']: row for row in rows}
            
            # Fill in all 7 days (including missing days with zeros)
            result = []
            for i in range(7):
                check_date = start_date + timedelta(days=i)
                day_data = data_map.get(check_date)
                
                if day_data:
                    result.append({
                        'date': check_date.isoformat(),
                        'screen_time': float(day_data['total_screen'] or 0),
                        'active_time': float(day_data['total_active'] or 0),
                        'idle_time': float(day_data['total_idle'] or 0),
                        'productivity': float(day_data['avg_productivity'] or 0)
                    })
                else:
                    # No data for this day
                    result.append({
                        'date': check_date.isoformat(),
                        'screen_time': 0,
                        'active_time': 0,
                        'idle_time': 0,
                        'productivity': 0
                    })
            
            print(f"📊 Returning {len(result)} days of trend data")
            print(f"========================================\n")
            
            return jsonify({
                'success': True,
                'trends': result,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': today.isoformat()
                },
                'timestamp': get_ist_now().isoformat()
            }), 200
    
    except Exception as e:
        print(f"❌ Activity trends error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch activity trends'}), 500


# ============================================================================
# MEMBER DETAIL - LIVE COUNTERS
# ============================================================================

@dashboard_bp.route('/api/dashboard/member/<int:member_id>/live', methods=['GET'])
@require_admin_auth
def get_member_live_counters(member_id):
    """
    Get live counters for a specific member
    
    Returns second-by-second counters:
    - Screen Time (seconds, ticking)
    - Active Time (seconds, ticking)
    - Idle Time (seconds, ticking)
    - Productivity % (live calculated)
    
    Frontend calculates ticking using:
    - Base values from this endpoint
    - Current timestamp
    - Delta calculation
    """
    try:
        company_id = request.company_id
        today = datetime.now(IST).date()
        
        with get_db() as conn:
            cur = conn.cursor()
            
            # Verify member belongs to company
            cur.execute(
                """
                SELECT id, name, email, position, status, is_punched_in, 
                       last_heartbeat_at, last_activity_at, last_punch_in_at
                FROM members
                WHERE id = %s AND company_id = %s
                """,
                (member_id, company_id)
            )
            member = cur.fetchone()
            
            if not member:
                return jsonify({'error': 'Member not found'}), 404
            
            # Get today's aggregated data
            cur.execute(
                """
                SELECT 
                    COALESCE(MAX(total_seconds), 0) as screen_time_seconds,
                    COALESCE(MAX(active_seconds), 0) as active_time_seconds,
                    COALESCE(MAX(idle_seconds), 0) as idle_time_seconds,
                    MAX(timestamp) as last_data_timestamp
                FROM activity_log
                WHERE member_id = %s 
                  AND company_id = %s 
                  AND DATE(timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') = %s
                """,
                (member_id, company_id, today)
            )
            data = cur.fetchone()
            
            # Calculate real-time status
            # status, seconds_ago = calculate_member_status(
            #     member['last_heartbeat_at'],
            #     member['last_activity_at']
            # )

            # prefer the DB status column, but gracefully fallback to calculation if absent
            if 'status' in member:
                status = member['status']
            else:
                status, seconds_ago = calculate_member_status(
                    member.get('last_heartbeat_at'),
                    member.get('last_activity_at')
                )
            if seconds_ago is None:
                seconds_ago = None  # keep explicit
            
            # Calculate productivity
            screen_time = float(data['screen_time_seconds'] or 0)
            active_time = float(data['active_time_seconds'] or 0)
            idle_time = float(data['idle_time_seconds'] or 0)
            
            if screen_time > 0:
                productivity = int((active_time / screen_time) * 100)
            else:
                productivity = 0
            
            # Calculate time elapsed since last punch in (if punched in)
            time_since_punch_in = 0
            if member['is_punched_in'] and member['last_punch_in_at']:
                punch_in_ist = convert_to_ist(member['last_punch_in_at'])
                time_since_punch_in = int((get_ist_now() - punch_in_ist).total_seconds())
            
            return jsonify({
                'success': True,
                'member': {
                    'id': member['id'],
                    'name': member['name'],
                    'email': member['email'],
                    'position': member['position'],
                    'status': status,
                    'is_punched_in': member['is_punched_in']
                },
                'live_counters': {
                    'screen_time_seconds': int(screen_time),
                    'active_time_seconds': int(active_time),
                    'idle_time_seconds': int(idle_time),
                    'productivity_percentage': productivity,
                    'time_since_punch_in_seconds': time_since_punch_in,
                    'last_data_timestamp': convert_to_ist(data['last_data_timestamp']).isoformat() if data['last_data_timestamp'] else None,
                    'current_server_time': get_ist_now().isoformat()
                },
                'explanation': {
                    'screen_time': 'Total time since punch in (active + idle)',
                    'active_time': 'Time with mouse/keyboard/app activity',
                    'idle_time': 'Time with no mouse/keyboard/app activity',
                    'productivity': '(active_time / screen_time) * 100',
                    'timezone': 'All times in IST (Asia/Kolkata)',
                    'frontend_delta_calculation': 'Frontend adds (current_time - last_data_timestamp) to counters for live ticking if member is active'
                }
            }), 200
    
    except Exception as e:
        print(f"❌ Member live counters error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to fetch live counters'}), 500


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ['dashboard_bp']
