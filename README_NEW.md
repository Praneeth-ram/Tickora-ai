# Tickora AI — Multi-Tenant Intelligent Attendance Chatbot

## Project Overview

**Tickora AI** is an AI-powered chatbot integrated into the Tickora attendance management application. It enables employees to ask natural-language questions about attendance, leave requests, work-from-home requests, timesheets, holidays, and work schedules.

The chatbot uses a **hybrid architecture combining a fine-tuned language model, dynamic database schema discovery, an approved operation registry, and PostgreSQL query execution**:

- The model interprets user questions and generates structured query plans
- The backend validates those plans, enforces tenant and user permissions, retrieves information from PostgreSQL, and generates answers grounded in actual query results
- The system is multi-tenant capable, using a shared model with tenant-aware schema discovery
- No model retraining is needed when new organizations are added

### Core Principle

> **The model decides what the user is asking for. The backend decides what the user is allowed to access and executes the operation.**

The model must never independently select the tenant, override the authenticated employee identity, access arbitrary tables, or execute unrestricted generated SQL.

---

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, Vite |
| Backend API | Python, FastAPI |
| Database | PostgreSQL |
| Database integration | SQLAlchemy |
| Authentication | Existing JWT/session authentication |
| Request validation | Pydantic |
| Model framework | Hugging Face Transformers |
| Fine-tuning | Supervised fine-tuning with PEFT/LoRA or QLoRA |
| Training environment | Google Colab |
| Model output | Structured JSON query plans |
| Testing | pytest |
| Prometheus metrics | Built-in FastAPI integration |

---

## What Is Completed

### 2.1 Platform

- Model runs in-process; response about 5 to 6 seconds (was about 60s)
- Single JSON error format: `detail` plus `error.code`, `error.message`, `error.details`
- Login rate limit: 5 failures per minute per IP and per email (429 `rate_limited`)
- JWT lifetime 60 minutes. Settings read through `get_settings()`.
- Dependencies cleaned; ML packages in the `llm` optional group
- Date range limit 366 days; inverted ranges rejected with 400

### 2.2 Database and Roles

- Migration head `20261104_add_roles`: `employees.role` in (`employee`, `admin`, `super_admin`), default `employee`
- Read-only role `tickora_agent`: writes rejected (verified)
- `AGENT_DATABASE_URL` reaches the process through settings (fixed earlier: the agent engine had silently used the owner account)

### 2.3 Access Control

- `access_policy.py`: role loaded from the database on every request, default-deny entities, row-level `scope_clause`, super-admin-only fields
- Executor applies the policy in every branch, and personal entities also filter on `self_employee_id`
- Named-person lookup within scope; out-of-scope and unknown names share one message
- Third-person wording for answers about a colleague
- Team attendance view for admins (department) and super admins (organization, grouped by department). Employees are refused
- `AccessDenied` routed through `_execute`, `run_llm_chat`, and `execution_node` (verified)
- Duplicate audit line removed; one audit line per decision

### 2.4 Chat and Orchestration

- LangGraph graph enabled. Parity checked: 30 single-topic and 10 compound questions match the direct path on the baseline
- Compound questions (two topics) are split and answered
- Payroll single-metric questions return the most recent period
- "Remaining loan amount and holiday" compound question now answers both parts

### 2.5 Tests

- 156 tests passing (`uv run pytest -q backend`)
- Access matrix (database), write-rejection, injection, enumeration, and team view tests exist and pass

### 2.6 Parity Run (policy on)

- EMP001 and EMP002 single-topic and compound runs completed and compared

---

## Known Defects (to Fix)

| Defect | Symptom | Expected |
|---|---|---|
| DEFECT-1 | Calendar questions refused as "person not found" (e.g. "Is October 31 a holiday?") | "There are no holidays on 31 October 2026." (not refused) |
| DEFECT-2 | Attendance part of compound question uses wrong month | Each part keeps its own named date |

---

## Pending Tasks (In Order)

### Phase A: Regression and Parity (Current)

- **T1**: Fix DEFECT-1 — replace `NAME_RE`/`names_a_person` with version that excludes calendar/question words
- **T2**: Confirm the task-scope change (prove `assigned_pending` = 0, `managed_pending` = 3)
- **T3**: Create `docs/parity_log.md` with one row per differing answer
- **T4**: Phase 3 answer-quality items (penalty-deduction lookup, active loans count, status questions, remove duplicate wording "0 hours and 0 minutes (0 minutes)", date-less questions use current period)
- **T5**: Investigate DEFECT-2 (month in compound attendance part) — fix so each part keeps its own named date

### Phase B: Hardening

- **T6**: Team view polish — show department names instead of IDs if departments table exists
- **T7**: Combined answer presentation (DEFECT-4) — decide rule for combined answers containing a table

### Phase C: Deployment

- **T10**: Durable audit — write audit records to a table with timestamp, request id, employee id, role, entity, decision
- **T11**: CORS from configuration — replace hard-coded `allow_origins` list with `CORS_ORIGINS` from settings
- **T12**: Dead code — remove unused imports/helpers/commented-out blocks in `backend/main.py`
- **T13**: Per-user chat rate limit — limit `/api/chat/{employee_code}` per user (e.g. 30 requests per minute)

### Phase D: Release

- **T14**: Docker stack — build and run, verify `/health` returns `status: ok`
- **T15**: Credentials — confirm test passwords were rotated; search for leftovers of `TickoraDev`/`TestAdmin`
- **T16**: Merge `feature/langgraph-rbac` into main line after Phase A checks pass. Tag the release.

---

## Definition of Done (Initial Implementation)

The initial implementation is complete only when:

- [ ] The actual tenant schema is verified and mapped
- [ ] Tenant provisioning and resolution work
- [ ] Cross-tenant access is blocked and tested
- [ ] The schema catalog discovers metadata per tenant
- [ ] The operation registry exposes only approved operations
- [ ] Query-plan validation rejects malformed and unauthorized requests
- [ ] The query engine executes parameterized queries safely
- [ ] The training dataset matches the production query-plan schema
- [ ] The fine-tuned model passes held-out evaluation
- [ ] FastAPI integrates model inference and database retrieval
- [ ] React displays accurate answers and clarification prompts
- [ ] Tests cover security, correctness, and error handling
- [ ] Deployment and monitoring procedures are documented

---

## Architecture

```
React Chat UI
      |
      v
FastAPI Chat Endpoint
      |
    +---- Authentication and Authorization
    +---- Tenant Resolver
    |          |
    |          v
    |     Organization Registry
    |
    +---- Fine-Tuned Model
    |          |
    |          v
    |     Structured Query Plan (JSON)
    |
    +---- Schema Catalog
    |
    +---- Operation Registry
    |
    +---- Query Plan Validator
    |
    +---- Dynamic Query Execution
    |          |
    |          v
    |       PostgreSQL
    |
    +---- Response Generator
           |
           v
      React Response
```

---

## Security Requirements

Security is part of the core architecture, not a later enhancement:

- Trusted tenant resolution
- Authentication on every chat request
- Employee-level row scoping
- Role-based permissions where required
- Strict operation and field allowlists
- Parameterized SQL
- Safely quoted database identifiers
- Read-only database access for read-only chatbot operations
- Query timeouts and result limits
- Rate limiting
- Safe handling of model output
- Protected secrets and database credentials
- Minimal logging of sensitive information
- Cross-tenant security tests
- Auditable operation execution

Do not permit the model to execute arbitrary SQL, choose a schema, change authentication context, or grant itself additional permissions.

State-changing actions such as clock-in/clock-out operations, leave approvals, and WFH approvals must use separately authorized business workflows. The initial chatbot should focus on approved read-only operations unless a write workflow is explicitly designed and tested.