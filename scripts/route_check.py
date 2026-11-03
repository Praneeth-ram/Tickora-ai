"""Run a question set through /api/chat and save the results to a CSV for review.

Usage (PowerShell):
    $env:TICKORA_TOKEN = "<access_token from /api/auth/login>"
    $env:TICKORA_EMPLOYEE_CODE = "EMP001"
    uv run python -m scripts.route_check
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
OUTPUT = "route_check_results.csv"

QUESTIONS = [
    # Attendance
    "What was my clock-in time yesterday?",
    "What was my clock-out time on October 5?",
    "How many days was I present this month?",
    "Show my attendance records for October.",
    "How many hours did I work last week?",
    # Leave
    "How many leave days have I used?",
    "What is my remaining leave balance?",
    "What is the status of my leave request?",
    "Which leave types are available?",
    "Show my leave history.",
    # Payroll
    "What is my salary for October?",
    "What is my gross salary?",
    "What amount was deducted?",
    "What is my net salary?",
    "Show my payroll history.",
    # Loan
    "What is my loan request status?",
    "What is the total amount of my emergency loan?",
    "What amount has been deducted from my penalty deduction?",
    "What is the remaining amount for my emergency loan?",
    "Show my loan applications.",
    "How many loans are currently active?",
    # Tasks
    "How many tasks are assigned to me?",
    "Show my completed tasks.",
    "How many pending tasks do I have?",
    # Timesheets
    "Show my timesheets for October.",
    # WFH
    "What is the status of my WFH request?",
    "How many WFH requests have I submitted?",
    # Holidays
    "What are the upcoming holidays?",
    "Is October 31 a holiday?",
    "Show the holidays for this year.",
]


def ask(question: str):
    body = json.dumps({"question": question, "session_id": "route-check"}).encode("utf-8")
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