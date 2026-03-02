import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import fetch_all
from admin_auth_routes import generate_admin_jwt
import requests

admins = fetch_all('SELECT id, email, company_id FROM admin_users LIMIT 1')
if not admins:
    print('No admin users in DB')
    sys.exit(1)
admin = admins[0]
admin_id = admin['id']
email = admin['email']
company_id = admin['company_id']

print('Using admin:', admin_id, email, 'company:', company_id)

token = generate_admin_jwt(admin_id, company_id, email, 'access')
print('Generated token (first 80 chars):', token[:80])

url = os.getenv('BACKEND_URL', 'http://127.0.0.1:10000') + '/api/attendance/members'
print('Fetching:', url)
resp = requests.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=10)
print('Status:', resp.status_code)
print('Response:', resp.json())
