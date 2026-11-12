import json
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8000/api/auth/login"

for attempt in range(1, 8):
    data = json.dumps({"email": "nobody@example.test", "password": "wrong-password"}).encode("utf-8")
    request = urllib.request.Request(
        URL, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    print(f"attempt {attempt}: {status}")