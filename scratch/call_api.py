import urllib.request
import json
import time

url = "http://127.0.0.1:8765/documents/baf461e9c2764a5ba9000a48772f846c/planning-jobs"
payload = json.dumps({"request": "thay doi hop 30x60 day 2 mm thanh day 1.2 mm", "whole_document": True}).encode("utf-8")
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

resp = urllib.request.urlopen(req)
data = json.loads(resp.read().decode("utf-8"))
job_id = data["id"]
print("Job submitted:", job_id)

for _ in range(60):
    time.sleep(2)
    status_url = f"{url}/{job_id}"
    s_resp = urllib.request.urlopen(status_url)
    s_data = json.loads(s_resp.read().decode("utf-8"))
    status = s_data.get("status")
    phase = s_data.get("phase")
    message = s_data.get("message")
    print(f"Status: {status}, Phase: {phase}, Message: {message}")
    if status in ("finished", "failed", "cancelled"):
        if "plan" in s_data:
            plan = s_data["plan"]
            print("Plan summary:", plan.get("summary"))
            print("Execution available:", s_data.get("execution_available"))
            print("Questions:", plan.get("questions"))
            print("Warnings:", plan.get("warnings"))
            print("Edit gate mode:", s_data.get("edit_gate", {}).get("mode"))
            print("Operations count:", len(plan.get("operations", [])))
        break
