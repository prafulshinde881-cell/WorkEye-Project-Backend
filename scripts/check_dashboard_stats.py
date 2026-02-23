import os, sys, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import fetch_all
from admin_auth_routes import generate_admin_jwt

admins = fetch_all('SELECT id, email, company_id FROM admin_users LIMIT 1')
if not admins:
    print('No admin users in DB')
    sys.exit(1)
admin = admins[0]
print('Using admin:', admin)
token = generate_admin_jwt(admin['id'], admin['company_id'], admin['email'], 'access')
url = os.getenv('BACKEND_URL', '') + '/api/dashboard/stats'
print('Fetching', url)
resp = requests.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=10)
print('Status:', resp.status_code)
print('JSON payload:', resp.json())
