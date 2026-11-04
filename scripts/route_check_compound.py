"""Route check for compound questions (two topics in one message).

Usage (PowerShell):
    $env:TICKORA_TOKEN = "<access_token>"
    $env:TICKORA_EMPLOYEE_CODE = "EMP001"
    uv run python -m scripts.route_check_compound
"""
import csv
import json
import os
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
TOKEN = os.environ["TICKORA_TOKEN"]
EMPLOYEE_CODE = os.environ.get("TICKORA_EMPLOYEE_CODE", "EMP001")
OUTPUT = os.environ.get("ROUTE_CHECK_OUTPUT", "compound_false.csv")

QUESTIONS = [
    "How many leave days did I use and what holidays are in October?",
    "Show my leave history and my WFH requests.",
    "What is my gross salary and how many tasks are assigned to me?",
    "Is October 31 a holiday and what was my clock-in time on October 5?",
    "How many leave types are there and what is my leave balance?",
    "Show my timesheets for October and my loan applications.",
    "What is my remaining emergency loan amount and is October 2 a holiday?",
    "How many WFH requests have I submitted and how many holidays are there this year?",
    "What is my net salary and show my leave history.",
    "Clock in and clock out on October 5 and is October 31 a holiday?",
]


def ask(question: str):
    body = json.dumps({"question": question, "session_id": "route-check-compound"}).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE}/api/chat/{EMPLOYEE_CODE}",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            status, payload = response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        status, payload = exc.code, json.loads(exc.read() or b"{}")
    return status, payload, time.perf_counter() - started


def main():
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["question", "http_status", "intent", "answer", "seconds"])
        for question in QUESTIONS:
            status, payload, seconds = ask(question)
            answer = payload.get("answer") or payload.get("detail") or ""
            writer.writerow([question, status, payload.get("intent"), answer, f"{seconds:.1f}"])
            print(f"{status}  {seconds:5.1f}s  {question}")
    print(f"\nSaved to {OUTPUT}")


if __name__ == "__main__":
    main()