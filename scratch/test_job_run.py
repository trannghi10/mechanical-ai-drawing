import urllib.request
import json
import time

url = "http://127.0.0.1:8765/documents/fdb1918fbce7401aa33c7738c4096b8f/planning-jobs"
payload = json.dumps({"request": "doi chieu dai tu 705mm thanh 700mm", "whole_document": True}).encode("utf-8")
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
    print(f"Status: {status}, Phase: {phase}")
    if status in ("finished", "failed", "cancelled", "ready", "resolved"):
        print("Final message:", message)
        if "plan" in s_data:
            plan = s_data["plan"]
            print("Plan summary:", plan.get("summary"), flush=True)
            print("Execution available:", s_data.get("execution_available"), flush=True)
            print("Questions:", plan.get("questions"), flush=True)
            print("Warnings:", plan.get("warnings"), flush=True)
            print("Operations count:", len(plan.get("operations", [])), flush=True)
            for op in plan.get("operations", []):
                print("  Op:", op.get("action"), op.get("ref"), op.get("before"), "->", op.get("after"))
        break
