import calendar
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.db import engine
from sqlalchemy import inspect, text

random.seed(42)

EXPECTED_DB = "tickora_ai_dev"
END_DATE = date.today()
START_DATE = END_DATE - timedelta(days=548)

REQUIRED_TABLES = {
    "organizations", "departments", "teams", "employees",
    "work_schedules", "schedule_days", "employee_schedule_assignments",
    "holiday_calendars", "holidays", "employee_holiday_assignments",
    "attendance_records", "attendance_punches", "leave_types",
    "leave_balances", "leave_requests", "leave_approvals",
    "wfh_requests", "wfh_approvals", "projects", "timesheets",
    "timesheet_entries", "payroll_periods", "payroll_summaries",
    "business_metrics", "conversation_sessions", "conversation_messages",
    "query_audit_logs", "user_feedback", "attendance_adjustments",
}

def month_start(d):
    return d.replace(day=1)

def next_month(d):
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)

def insert_row(conn, table, values, returning="id"):
    columns = list(values)
    sql = (
        f'INSERT INTO "{table}" '
        f'({", ".join(chr(34) + c + chr(34) for c in columns)}) '
        f'VALUES ({", ".join(":" + c for c in columns)})'
    )
    if returning:
        sql += f' RETURNING "{returning}"'
        return conn.execute(text(sql), values).scalar_one()
    conn.execute(text(sql), values)
    return None

def main():
    database = engine.url.database
    if database != EXPECTED_DB:
        raise RuntimeError(
            f"Safety stop: expected database {EXPECTED_DB!r}, "
            f"but DATABASE_URL points to {database!r}."
        )

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = REQUIRED_TABLES - existing
    if missing:
        raise RuntimeError(f"Missing expected tables: {sorted(missing)}")

    # Check all application tables before inserting anything.
    with engine.connect() as conn:
        for table in sorted(REQUIRED_TABLES):
            count = conn.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar_one()
            if count:
                raise RuntimeError(
                    f"Safety stop: {table} already contains {count} rows. "
                    "This seeder will not mix with existing data."
                )

    with engine.begin() as conn:
        # 1. Organization
        org_id = insert_row(conn, "organizations", {
            "name": "Tickora Demo Organization",
            "timezone": "Asia/Kolkata",
            "country_code": "IN",
            "is_active": True,
        })

        # 2. Departments and teams
        department_names = [
            "Engineering", "Human Resources", "Finance",
            "Operations", "Product",
        ]
        department_ids = {}
        team_ids = {}

        for department_name in department_names:
            department_id = insert_row(conn, "departments", {
                "organization_id": org_id,
                "name": department_name,
            })
            department_ids[department_name] = department_id

            team_ids[department_name] = []
            for suffix in ["A", "B"]:
                team_ids[department_name].append(
                    insert_row(conn, "teams", {
                        "department_id": department_id,
                        "name": f"{department_name} Team {suffix}",
                    })
                )

        # 3. Schedule and weekdays (PostgreSQL DOW: Sunday=0).
        schedule_id = insert_row(conn, "work_schedules", {
            "organization_id": org_id,
            "name": "Standard India Weekday Schedule",
            "schedule_type": "fixed",
            "is_active": True,
        })

        for dow in range(7):
            working = dow in range(1, 6)
            insert_row(conn, "schedule_days", {
                "schedule_id": schedule_id,
                "day_of_week": dow,
                "start_time": time(9, 30) if working else None,
                "end_time": time(18, 30) if working else None,
                "break_minutes": 60 if working else 0,
                "required_minutes": 480 if working else 0,
                "is_working_day": working,
            })

        # 4. Employees: insert managers before their reports.
        people = [
            ("EMP001", "Aarav Sharma", "Engineering", "Engineering Manager"),
            ("EMP002", "Diya Iyer", "Human Resources", "HR Manager"),
            ("EMP003", "Arjun Kumar", "Finance", "Finance Manager"),
            ("EMP004", "Meera Nair", "Operations", "Operations Manager"),
            ("EMP005", "Ishaan Reddy", "Product", "Product Manager"),
            ("EMP006", "Ananya Rao", "Engineering", "Software Engineer"),
            ("EMP007", "Vihaan Patel", "Engineering", "Backend Engineer"),
            ("EMP008", "Aadhya Menon", "Engineering", "Frontend Engineer"),
            ("EMP009", "Kabir Das", "Engineering", "QA Engineer"),
            ("EMP010", "Saanvi Gupta", "Engineering", "AI Engineer"),
            ("EMP011", "Reyansh Verma", "Human Resources", "HR Executive"),
            ("EMP012", "Myra Krishnan", "Human Resources", "Recruiter"),
            ("EMP013", "Advait Shah", "Finance", "Accountant"),
            ("EMP014", "Sara Thomas", "Finance", "Financial Analyst"),
            ("EMP015", "Krishna Joshi", "Operations", "Operations Analyst"),
            ("EMP016", "Ira Pillai", "Operations", "Support Specialist"),
            ("EMP017", "Rohan Bhat", "Product", "Product Analyst"),
            ("EMP018", "Tara Singh", "Product", "UX Designer"),
            ("EMP019", "Dev Malhotra", "Engineering", "DevOps Engineer"),
            ("EMP020", "Nila George", "Engineering", "Data Engineer"),
        ]

        employee_ids = {}
        manager_codes = {
            "Engineering": "EMP001",
            "Human Resources": "EMP002",
            "Finance": "EMP003",
            "Operations": "EMP004",
            "Product": "EMP005",
        }

        for code, name, dept, designation in people:
            is_manager = code in manager_codes.values()
            manager_code = None if is_manager else manager_codes[dept]
            joined = START_DATE - timedelta(days=random.randint(0, 500))

            employee_id = insert_row(conn, "employees", {
                "organization_id": org_id,
                "department_id": department_ids[dept],
                "team_id": team_ids[dept][0 if int(code[-1]) % 2 else 1],
                "manager_id": employee_ids.get(manager_code),
                "employee_code": code,
                "full_name": name,
                "email": f"{code.lower()}@tickora-demo.example",
                "designation": designation,
                "employment_type": "full_time",
                "date_joined": joined,
                "date_left": None,
                "is_active": True,
            })
            employee_ids[code] = employee_id

            insert_row(conn, "employee_schedule_assignments", {
                "employee_id": employee_id,
                "schedule_id": schedule_id,
                "effective_from": joined,
                "effective_to": None,
            }, returning=None)

        # 5. Holiday calendar and sample holidays.
        calendar_id = insert_row(conn, "holiday_calendars", {
            "organization_id": org_id,
            "name": "India Demo Holiday Calendar",
            "country_code": "IN",
            "region": "Tamil Nadu",
        })

        sample_holidays = [
            (1, 1, "New Year's Day"),
            (1, 26, "Republic Day"),
            (5, 1, "Labour Day"),
            (8, 15, "Independence Day"),
            (10, 2, "Gandhi Jayanti"),
            (12, 25, "Christmas Day"),
        ]

        holiday_dates = set()
        for year in range(START_DATE.year, END_DATE.year + 1):
            for month, day, name in sample_holidays:
                holiday_date = date(year, month, day)
                if START_DATE <= holiday_date <= END_DATE:
                    insert_row(conn, "holidays", {
                        "calendar_id": calendar_id,
                        "holiday_date": holiday_date,
                        "name": name,
                        "holiday_type": "public",
                    })
                    holiday_dates.add(holiday_date)

        for employee_id in employee_ids.values():
            insert_row(conn, "employee_holiday_assignments", {
                "employee_id": employee_id,
                "calendar_id": calendar_id,
            }, returning=None)

        # 6. Leave types and leave balances.
        leave_type_ids = {}
        for code, name, paid in [
            ("CASUAL", "Casual Leave", True),
            ("SICK", "Sick Leave", True),
            ("EARNED", "Earned Leave", True),
            ("UNPAID", "Unpaid Leave", False),
        ]:
            leave_type_ids[code] = insert_row(conn, "leave_types", {
                "organization_id": org_id,
                "code": code,
                "name": name,
                "is_paid": paid,
            })

        leave_requests = []
        for employee_code, employee_id in employee_ids.items():
            for leave_code, leave_type_id in leave_type_ids.items():
                used = Decimal("0.00")
                pending = Decimal("0.00")
                if leave_code == "CASUAL":
                    allocated = Decimal("12.00")
                elif leave_code == "SICK":
                    allocated = Decimal("10.00")
                elif leave_code == "EARNED":
                    allocated = Decimal("15.00")
                else:
                    allocated = Decimal("0.00")

                insert_row(conn, "leave_balances", {
                    "employee_id": employee_id,
                    "leave_type_id": leave_type_id,
                    "year": END_DATE.year,
                    "allocated_days": allocated,
                    "used_days": used,
                    "pending_days": pending,
                }, returning=None)

        for _ in range(55):
            employee_code = random.choice(list(employee_ids))
            employee_id = employee_ids[employee_code]
            start = START_DATE + timedelta(
                days=random.randint(0, max(0, (END_DATE - START_DATE).days))
            )
            if start > END_DATE:
                start = END_DATE
            duration = random.randint(1, 3)
            end = min(start + timedelta(days=duration - 1), END_DATE)
            status = random.choices(
                ["approved", "pending", "rejected", "cancelled"],
                weights=[55, 20, 20, 5],
            )[0]
            leave_type_id = random.choice(list(leave_type_ids.values()))
            requested_days = Decimal(
                str(sum(
                    1 for offset in range((end - start).days + 1)
                    if (start + timedelta(days=offset)).weekday() < 5
                    and (start + timedelta(days=offset)) not in holiday_dates
                ))
            )
            if requested_days <= 0:
                continue

            request_id = insert_row(conn, "leave_requests", {
                "employee_id": employee_id,
                "leave_type_id": leave_type_id,
                "start_date": start,
                "end_date": end,
                "requested_days": requested_days,
                "reason": random.choice([
                    "Personal work", "Family commitment",
                    "Medical appointment", "Planned vacation",
                ]),
                "status": status,
                "applied_at": datetime.combine(
                    max(START_DATE, start - timedelta(days=random.randint(1, 15))),
                    time(10, 0),
                ),
            })
            leave_requests.append({
                "id": request_id,
                "employee_id": employee_id,
                "start": start,
                "end": end,
                "status": status,
                "days": requested_days,
            })

            if status in ("approved", "rejected"):
                manager_id = None
                for code, eid in employee_ids.items():
                    if eid == employee_id:
                        dept = next(p[2] for p in people if p[0] == code)
                        manager_id = employee_ids.get(manager_codes[dept])
                        break
                insert_row(conn, "leave_approvals", {
                    "leave_request_id": request_id,
                    "approver_id": manager_id,
                    "decision": status,
                    "comments": (
                        "Approved in demo data"
                        if status == "approved"
                        else "Rejected in demo data"
                    ),
                    "decided_at": datetime.combine(
                        min(END_DATE, end + timedelta(days=1)),
                        time(11, 0),
                    ),
                }, returning=None)

        # 7. WFH requests and approvals.
        wfh_requests = []
        for _ in range(40):
            employee_code = random.choice(list(employee_ids))
            employee_id = employee_ids[employee_code]
            start = START_DATE + timedelta(
                days=random.randint(0, max(0, (END_DATE - START_DATE).days))
            )
            end = min(start + timedelta(days=random.randint(0, 2)), END_DATE)
            status = random.choices(
                ["approved", "pending", "rejected", "cancelled"],
                weights=[55, 20, 20, 5],
            )[0]

            request_id = insert_row(conn, "wfh_requests", {
                "employee_id": employee_id,
                "start_date": start,
                "end_date": end,
                "reason": random.choice([
                    "Remote work day", "Home appointment",
                    "Travel constraint", "Focus work",
                ]),
                "status": status,
                "applied_at": datetime.combine(
                    max(START_DATE, start - timedelta(days=2)),
                    time(9, 0),
                ),
            })
            wfh_requests.append({
                "id": request_id,
                "employee_id": employee_id,
                "start": start,
                "end": end,
                "status": status,
            })

            if status in ("approved", "rejected"):
                insert_row(conn, "wfh_approvals", {
                    "wfh_request_id": request_id,
                    "approver_id": None,
                    "decision": status,
                    "comments": f"{status.title()} in demo data",
                    "decided_at": datetime.combine(
                        min(END_DATE, end + timedelta(days=1)),
                        time(11, 0),
                    ),
                }, returning=None)

        # 8. Projects.
        project_ids = []
        for code, name in [
            ("TICKORA", "Tickora Platform"),
            ("AI-CHAT", "AI Attendance Assistant"),
            ("DATA-OPS", "Data Operations"),
            ("INTERNAL", "Internal Tools"),
        ]:
            project_ids.append(insert_row(conn, "projects", {
                "organization_id": org_id,
                "name": name,
                "code": code,
                "is_active": True,
            }))

        # 9. Attendance records and punches.
        attendance_count = 0
        punch_count = 0
        current = START_DATE

        while current <= END_DATE:
            if current.weekday() < 5 and current not in holiday_dates:
                for employee_code, employee_id in employee_ids.items():
                    joined = next(
                        p for p in people if p[0] == employee_code
                    )
                    # Re-read the actual joining date for this employee.
                    employee_joined = conn.execute(text(
                        "SELECT date_joined FROM employees WHERE id=:id"
                    ), {"id": employee_id}).scalar_one()

                    if current < employee_joined:
                        continue

                    approved_leave = next((
                        req for req in leave_requests
                        if req["employee_id"] == employee_id
                        and req["status"] == "approved"
                        and req["start"] <= current <= req["end"]
                    ), None)

                    if approved_leave:
                        status = "on_leave"
                        clock_in = clock_out = None
                        worked = 0
                        location = "office"
                        late = False
                    else:
                        approved_wfh = any(
                            req["employee_id"] == employee_id
                            and req["status"] == "approved"
                            and req["start"] <= current <= req["end"]
                            for req in wfh_requests
                        )
                        roll = random.random()
                        if roll < 0.035:
                            status = "absent"
                            clock_in = clock_out = None
                            worked = 0
                            location = "office"
                            late = False
                        elif roll < 0.065:
                            status = "half_day"
                            worked = random.randint(220, 260)
                            clock_in = datetime.combine(
                                current, time(9, random.randint(30, 55))
                            )
                            clock_out = clock_in + timedelta(minutes=worked + 60)
                            location = "remote" if approved_wfh else "office"
                            late = clock_in.time() > time(9, 45)
                        else:
                            late = random.random() < 0.15
                            status = "late" if late else (
                                "work_from_home" if approved_wfh else "present"
                            )
                            worked = random.randint(450, 510)
                            start_time = time(
                                9, random.randint(46, 59)
                            ) if late else time(
                                9, random.randint(20, 40)
                            )
                            clock_in = datetime.combine(current, start_time)
                            clock_out = clock_in + timedelta(
                                minutes=worked + 60
                            )
                            location = "remote" if approved_wfh else "office"

                    record_id = insert_row(conn, "attendance_records", {
                        "employee_id": employee_id,
                        "attendance_date": current,
                        "schedule_id": schedule_id,
                        "status": status,
                        "clock_in": clock_in,
                        "clock_out": clock_out,
                        "worked_minutes": worked,
                        "regular_minutes": min(worked, 480),
                        "overtime_minutes": max(0, worked - 480),
                        "break_minutes": 60 if worked else 0,
                        "is_late": late,
                        "work_location": location,
                        "notes": None,
                    })
                    attendance_count += 1

                    if clock_in is not None and clock_out is not None:
                        insert_row(conn, "attendance_punches", {
                            "attendance_id": record_id,
                            "punched_at": clock_in,
                            "punch_type": "clock_in",
                            "source": "mobile",
                            "location_description": (
                                "Remote" if location == "remote" else "Office"
                            ),
                        }, returning=None)
                        insert_row(conn, "attendance_punches", {
                            "attendance_id": record_id,
                            "punched_at": clock_out,
                            "punch_type": "clock_out",
                            "source": "mobile",
                            "location_description": (
                                "Remote" if location == "remote" else "Office"
                            ),
                        }, returning=None)
                        punch_count += 2
            current += timedelta(days=1)

        # 10. Timesheets: weekly periods and entries.
        week_start = START_DATE - timedelta(days=START_DATE.weekday())
        while week_start <= END_DATE:
            week_end = week_start + timedelta(days=6)
            actual_end = min(week_end, END_DATE)

            for employee_id in employee_ids.values():
                if week_start > END_DATE:
                    continue

                status = random.choices(
                    ["approved", "submitted", "draft", "rejected"],
                    weights=[65, 20, 10, 5],
                )[0]
                submitted_at = (
                    datetime.combine(actual_end, time(18, 0))
                    if status in ("approved", "submitted", "rejected")
                    else None
                )
                approved_at = (
                    datetime.combine(actual_end, time(19, 0))
                    if status == "approved" else None
                )

                timesheet_id = insert_row(conn, "timesheets", {
                    "employee_id": employee_id,
                    "period_start": week_start,
                    "period_end": actual_end,
                    "status": status,
                    "submitted_at": submitted_at,
                    "approved_at": approved_at,
                })

                workday = max(week_start, START_DATE)
                while workday <= actual_end:
                    if workday.weekday() < 5 and workday not in holiday_dates:
                        if workday <= END_DATE:
                            insert_row(conn, "timesheet_entries", {
                                "timesheet_id": timesheet_id,
                                "project_id": random.choice(project_ids),
                                "work_date": workday,
                                "description": random.choice([
                                    "Feature development",
                                    "Bug fixing and testing",
                                    "Code review",
                                    "Documentation",
                                    "Project coordination",
                                ]),
                                "worked_minutes": random.choice(
                                    [360, 420, 450, 480]
                                ),
                            }, returning=None)
                    workday += timedelta(days=1)

            week_start += timedelta(days=7)

        # 11. Monthly payroll summaries.
        period_start = month_start(START_DATE)
        while period_start <= END_DATE:
            period_end = min(
                date(
                    period_start.year,
                    period_start.month,
                    calendar.monthrange(
                        period_start.year, period_start.month
                    )[1],
                ),
                END_DATE,
            )
            payroll_id = insert_row(conn, "payroll_periods", {
                "organization_id": org_id,
                "period_start": period_start,
                "period_end": period_end,
            })

            for employee_id in employee_ids.values():
                gross = Decimal(random.randrange(35000, 95001, 500)).quantize(
                    Decimal("0.01")
                )
                deduction = (gross * Decimal("0.12")).quantize(
                    Decimal("0.01")
                )
                insert_row(conn, "payroll_summaries", {
                    "payroll_period_id": payroll_id,
                    "employee_id": employee_id,
                    "gross_amount": gross,
                    "deduction_amount": deduction,
                    "net_amount": gross - deduction,
                    "currency": "INR",
                }, returning=None)

            period_start = next_month(period_start)

        # 12. Metrics available for future registered-query planning.
        metrics = [
            (
                "attendance_rate",
                "Attendance rate",
                "present and late attendance records divided by scheduled records",
            ),
            (
                "total_worked_hours",
                "Total worked hours",
                "sum of attendance_records.worked_minutes divided by 60",
            ),
            (
                "overtime_hours",
                "Overtime hours",
                "sum of attendance_records.overtime_minutes divided by 60",
            ),
        ]
        for key, description, definition in metrics:
            insert_row(conn, "business_metrics", {
                "metric_key": key,
                "description": description,
                "calculation_definition": definition,
                "is_enabled": True,
            }, returning=None)

        # Transaction commits automatically only if all inserts succeeded.
        print("Seed completed successfully.")
        print(f"Organization ID: {org_id}")
        print(f"Employees: {len(employee_ids)}")
        print(f"Attendance records: {attendance_count}")
        print(f"Attendance punches: {punch_count}")
        print(f"Date range: {START_DATE} through {END_DATE}")
        print("Conversation, audit, feedback, and adjustment tables remain empty.")

if __name__ == "__main__":
    main()
