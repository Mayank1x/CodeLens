"""Quick script to test all Phase 3 endpoints."""
import requests
import json
import time

BASE = "http://localhost:5000"

print("=" * 50)
print("1. Health Check")
print("=" * 50)
r = requests.get(f"{BASE}/health")
print(f"   Status: {r.status_code}")
print(f"   Response: {r.json()}")

print("\n" + "=" * 50)
print("2. Submit Review (POST /api/review)")
print("=" * 50)
code = """password = 'secret123'
query = "SELECT * FROM users WHERE id=" + user_id

def process(items=[]):
    try:
        result = do_something()
    except:
        pass
"""
r = requests.post(f"{BASE}/api/review", json={"code": code, "language": "python"})
print(f"   Status: {r.status_code}")
data = r.json()
print(f"   Response: {json.dumps(data, indent=4)}")
review_id = data.get("review_id")

print("\n" + "=" * 50)
print("3. Poll Review (GET /api/review/<id>)")
print("=" * 50)
# Poll a few times until complete
for i in range(5):
    time.sleep(2)
    r = requests.get(f"{BASE}/api/review/{review_id}")
    data = r.json()
    print(f"   Attempt {i+1}: status={data['status']}")
    if data["status"] in ("complete", "failed"):
        print(f"   Issues found: {data.get('issue_count', 'N/A')}")
        if "issues" in data:
            for issue in data["issues"]:
                print(f"     Line {issue['line_number']}: [{issue['severity']}] [{issue['source']}] {issue['message']}")
        break

print("\n" + "=" * 50)
print("4. History (GET /api/history)")
print("=" * 50)
r = requests.get(f"{BASE}/api/history")
print(f"   Status: {r.status_code}")
data = r.json()
print(f"   Total reviews: {data['total']}")
for rev in data["reviews"]:
    print(f"     {rev['id'][:8]}... | {rev['language']} | {rev['status']} | issues: {rev['issue_count']}")

print("\n" + "=" * 50)
print("5. Stats (GET /api/stats)")
print("=" * 50)
r = requests.get(f"{BASE}/api/stats")
print(f"   Status: {r.status_code}")
print(f"   Response: {json.dumps(r.json(), indent=4)}")

print("\n✅ All endpoints tested!")
