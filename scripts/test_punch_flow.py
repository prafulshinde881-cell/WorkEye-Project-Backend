import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import fetch_all
import requests, base64

# Find a member with active device
row = fetch_all('''
SELECT m.id as member_id, m.email, d.device_id, m.company_id
FROM members m
JOIN devices d ON d.member_id = m.id
LIMIT 1
''')
if not row:
    print('No member/device found')
    sys.exit(1)
row = row[0]
member_id = row['member_id']
email = row['email']
device = row['device_id']
company_id = row['company_id']
print('Using:', member_id, email, device, 'company', company_id)

# Punch in via attendance endpoint
backend = os.getenv('BACKEND_URL', 'https://workeye-project-backend.onrender.com')
print('Using backend:', backend)
pi_resp = requests.post(backend + '/api/attendance/punch-in', json={'member_email': email, 'company_id': company_id}, timeout=10)
print('Punch-in status:', pi_resp.status_code, pi_resp.text)

# Wait a bit then call tracker/punch-out
time.sleep(1)
tracker_token = base64.b64encode(f"{company_id}:test".encode()).decode()
to_resp = requests.post(backend + '/tracker/punch-out', json={'email': email, 'deviceid': device}, headers={'X-Tracker-Token': tracker_token}, timeout=10)
print('Tracker punch-out:', to_resp.status_code, to_resp.text)

# Fetch latest punch_logs for member
from db import fetch_all
rows = fetch_all('SELECT id, action, punch_in_time, punch_out_time, timestamp FROM punch_logs WHERE member_id = %s ORDER BY id DESC LIMIT 10', (member_id,))
for r in rows:
    print(r)
