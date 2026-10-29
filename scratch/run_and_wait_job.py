import urllib.request
import json
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')

url = "http://127.0.0.1:8765/documents/34ee84f35e1a44fb81c56044397a0fff/planning-jobs"
req_data = {
    "request": "Tất cả vật liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm",
    "whole_document": True
}

req = urllib.request.Request(
    url,
    data=json.dumps(req_data).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

print("Submitting job...")
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode('utf-8'))
    job_id = res['id']
    print(f"Job ID: {job_id}, initial status: {res.get('status')}")

job_url = f"{url}/{job_id}"
start = time.time()
while True:
    time.sleep(2)
    with urllib.request.urlopen(job_url) as resp:
        status_data = json.loads(resp.read().decode('utf-8'))
        status = status_data.get('status')
        phase = status_data.get('phase')
        msg = status_data.get('message')
        elapsed = round(time.time() - start, 1)
        print(f"[{elapsed}s] status={status}, phase={phase}, msg={msg}")
        if status in ('ready', 'failed', 'blocked', 'cancelled'):
            break

print("Final Job State:")
print(json.dumps(status_data, indent=2, ensure_ascii=False))
