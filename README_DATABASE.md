# Tickora AI — Database

Tickora AI uses PostgreSQL for employee profiles, credentials, attendance, and HR-related records. The FastAPI backend accesses it through SQLAlchemy and repository modules.

The database is the source of truth for employee and attendance information. The AI service should answer factual employee questions using records retrieved for the authenticated employee.

## Known tables

These columns were recorded during development. Confirm the live schema before using this document as a migration specification.

### `departments`

| Column | Type | Notes |
|---|---|---|
| `department_id` | `BIGINT` | Primary key |
| `department_name` | `VARCHAR` | Department name |
| `created_at` | `TIMESTAMPTZ` | Creation timestamp |

### `employees`

| Column | Type | Notes |
|---|---|---|
| `employee_id` | `BIGINT` | Primary key |
| `employee_code` | `VARCHAR` | Unique employee code |
| `full_name` | `VARCHAR` | Employee name |
| `email` | `VARCHAR` | Unique email |
| `department_id` | `BIGINT` | Foreign key to departments |
| `manager_id` | `BIGINT` | Nullable manager reference |
| `date_joined` | `DATE` | Joining date |
| `is_active` | `BOOLEAN` | Active employee flag |

### `employee_credentials`

| Column | Type | Notes |
|---|---|---|
| `credential_id` | `BIGINT` | Identity primary key |
| `employee_id` | `BIGINT` | Unique foreign key to `employees`, cascade delete |
| `password_hash` | `TEXT` | Password hash, never plaintext |
| `is_enabled` | `BOOLEAN` | Credential enabled flag |
| `created_at` | `TIMESTAMPTZ` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | Last update timestamp |

### `attendance_records`

| Column | Type | Notes |
|---|---|---|
| `attendance_id` | `BIGINT` | Primary key |
| `employee_id` | `BIGINT` | Foreign key to employees |
| `work_date` | `DATE` | Attendance date |
| `clock_in` | `TIMESTAMPTZ` | Nullable clock-in timestamp |
| `clock_out` | `TIMESTAMPTZ` | Nullable clock-out timestamp |
| `status` | `VARCHAR` | Attendance status |
| `work_location` | `VARCHAR` | Work location |
| `source` | `VARCHAR` | Record source |
| `created_at` | `TIMESTAMPTZ` | Creation timestamp |

### Other referenced tables
- `timesheets`
- `holidays`
- `leave_requests`
- `wfh_requests`
- `work_schedules`

Their exact columns, constraints, indexes, and relationships should be checked against the live database or migrations.

## Conceptual relationships

```text
departments
    |
    +----< employees >---- employees (manager relationship)
                |
                +----< employee_credentials
                +----< attendance_records
                +----< timesheets
                +----< leave_requests
                +----< wfh_requests
                +----< work_schedules

holidays: calendar/region lookup data
```

This is a conceptual overview; confirm actual foreign keys in PostgreSQL.

## Local development
The recorded development environment used PostgreSQL on Windows, with port `5433`. The actual connection string in your backend environment configuration is authoritative.

Typical workflow:
1. Start PostgreSQL.
2. Confirm the target database exists.
3. Configure the backend connection.
4. Create or migrate tables.
5. Seed development departments, employees, and sample HR records.
6. Test API routes through `http://127.0.0.1:8000/docs`.

Never include production credentials or real connection strings in this README.

## Inspect schema

In `psql`:

```sql
\dt public.*
\d+ public.employees
```

In pgAdmin, open the database, expand **Schemas → public → Tables**, and inspect columns and constraints.

## Data integrity and security
- Keep employee emails and employee codes unique.
- Each credential row belongs to one employee.
- Store only password hashes created by the backend hashing utility.
- Use `is_active` and `is_enabled` to disable access when needed.
- Do not commit production data or database backups to source control.
- Back up the database before schema changes and use versioned migrations where possible.
