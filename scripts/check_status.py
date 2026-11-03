import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZW1wbG95ZWVfY29kZSI6IkVNUDAwMSIsImlhdCI6MTc5MzY5NzMyNSwiZXhwIjoxNzkzNzAwOTI1fQ.EXvRTg8exHooeAzZ4_v3pYinzH422dWvE5i_8I-Df10"

CASES = [
    ("no token", "GET", "/api/holidays?start_date=2026-10-01&end_date=2026-10-31", None, 401),
    ("bad date range", "GET", "/api/attendance/EMP001?start_date=2026-10-31&end_date=2026-10-01", TOKEN, 400),
    ("range too long", "GET", "/api/attendance/EMP001?start_date=1900-01-01&end_date=2100-12-31", TOKEN, 400),
    ("unknown route", "GET", "/api/nothing-here", None, 404),
    ("missing body field", "POST", "/api/auth/login", None, 422),
]

for name, method, path, token, expected in CASES:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = b"{}" if method == "POST" else None
    request = urllib.request.Request(BASE + path, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(request) as response:
            status, text = response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read().decode()
    code = json.loads(text).get("error", {}).get("code") if text.startswith("{") else None
    verdict = "OK" if status == expected else "MISMATCH"
    print(f"{verdict:8} {name:20} expected {expected} got {status}  code={code}")