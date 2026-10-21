# Tickora AI Backend

FastAPI backend for Tickora AI, an employee attendance assistant connected to PostgreSQL.

## Technology
- Python, FastAPI, SQLAlchemy, PostgreSQL
- Uvicorn for local development
- PyJWT for JWT access tokens
- `pwdlib[argon2]` for password hashing
- PyTorch-based intent classification and chat service

## Features
- Employee email/password login
- Password-hash verification
- JWT token creation and validation
- Employee identity checks for employee-specific endpoints
- Attendance records and summaries
- Timesheets, leave requests, WFH requests, work schedules, and holiday lookup
- Chat endpoint that passes the authenticated employee ID to the AI service

## Main modules
- `backend/main.py` — API routes and login
- `backend/db.py` — SQLAlchemy engine
- `backend/dependencies/auth.py` — bearer-token validation and current employee lookup
- `backend/services/auth_service.py` — password and JWT utilities
- `backend/services/chat_service.py` — chat orchestration
- `backend/repositories/` — database access modules
- `ai_model/` — intent model and training utilities

Confirm exact paths against the current repository before publishing.

## Prerequisites
- Python version compatible with `pyproject.toml`
- `uv`
- PostgreSQL running and initialized
- Backend environment variables configured

## Environment
Configure your database connection using the variable names expected by `backend/db.py`. Set JWT values in the backend `.env` file:

```env
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Never commit `.env`, database passwords, JWT secrets, or employee credentials. Use a different secret in production.

## Install and run

```powershell
uv sync
uv run uvicorn backend.main:app --reload
```

Default local API URL: `http://127.0.0.1:8000`

Swagger documentation: `http://127.0.0.1:8000/docs`

Health check: `GET /health`

## Login
`POST /api/auth/login` accepts registered email and password:

```json
{
  "email": "employee@example.test",
  "password": "your-password"
}
```

A successful response returns an access token and employee profile. Protected requests should include:

```http
Authorization: Bearer <access_token>
```

## API routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/auth/login` | Email/password login |
| GET | `/api/attendance/{employee_code}` | Attendance records for a date range |
| GET | `/api/attendance/{employee_code}/summary` | Attendance summary |
| GET | `/api/timesheets/{employee_code}` | Timesheets |
| GET | `/api/leave/{employee_code}` | Leave requests |
| GET | `/api/wfh/{employee_code}` | Work-from-home requests |
| GET | `/api/holidays` | Holiday lookup |
| GET | `/api/schedules/{employee_code}` | Work schedule |
| POST | `/api/chat/{employee_code}` | AI chat |

Use `/docs` for current parameter requirements. Date parameters use `YYYY-MM-DD`.

## Employee password setup

The recorded local script can be run with:

```powershell
uv run python -m scripts.setup_employee_passwords
```

It prompts for passwords and stores hashes in `employee_credentials`. Do not store plaintext passwords.

## Security checklist
- Keep `.env` out of Git.
- Rotate any exposed secrets.
- Use HTTPS in deployment.
- Add login rate limiting before production.
- Ensure every employee-specific route validates JWT and matches the authenticated employee.
- Do not log passwords, tokens, or sensitive employee data.
