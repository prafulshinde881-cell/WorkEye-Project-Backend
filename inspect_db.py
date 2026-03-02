# simplified database inspection using existing connection helper
from db import get_db

with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='screenshots';")
    rows = cur.fetchall()
    print('screenshots columns:', rows)

    # also check devices table for our test device
    cur.execute("SELECT * FROM devices WHERE device_id = %s", ('22fc502a',))
    print('device rows for 22fc502a:', cur.fetchall())

    # and look up members for our test email
    cur.execute("SELECT id, company_id, email FROM members WHERE email = %s", ('ankit123@gmail.com',))
    print('members with email ankit123:', cur.fetchall())

    cur.execute("SELECT id, email FROM members WHERE id = %s", (92,))
    print('member 92 record:', cur.fetchall())
