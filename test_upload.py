import requests, json

url = 'http://127.0.0.1:10000/tracker/upload'
headers = {
    'Content-Type': 'application/json',
    'X-Tracker-Token': 'MjQ6alRCdlI3cGVYRE1jakhxRnQ1SDdIaVYySjA2M2VBYmhMMjA2WlJJOGxKdw=='
}
# prepare a tiny 1x1 white JPEG as base64
from PIL import Image
from io import BytesIO
import base64
img = Image.new('RGB',(1,1),color='white')
buf=BytesIO()
img.save(buf,format='JPEG')
screenshot_b64 = base64.b64encode(buf.getvalue()).decode()

data = {
    # use member ID 92's email, since device is registered to that member
    'email':'divesh1234@gmail.com',
    'deviceid':'22fc502a',
    'timestamp':'2026-03-02T10:36:00',
    'sessionstart':'2026-03-02T10:34:00',
    'lastactivity':'2026-03-02T10:36:00',
    'totalseconds':120,
    'activeseconds':120,
    'idleseconds':0,
    'lockedseconds':0,
    'idlefor':0,
    'isidle':False,
    'locked':False,
    'screenshot': screenshot_b64
}
r = requests.post(url, json=data, headers=headers)
print(r.status_code)
print(r.text)