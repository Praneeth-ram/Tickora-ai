# Tickora AI — Complete Application Audit

**Audit date:** 2026-11-26
**Scope:** Read-only code and configuration review; test directories and test cases were excluded.
**Runtime verification:** Not performed. Database mutations, migrations, model inference, test suites, and external service requests were not executed.

## 1. Executive Summary

The application has a strong architectural baseline: parameterized SQLAlchemy queries, an explicit operation allowlist, role-aware scope clauses, PostgreSQL RLS, JWT authentication, and an employee/session ownership model. However, several implementation defects materially affect authorization and follow-up behavior.

The most important confirmed defects are:

1. The chat-session migration does not create `last_plan`, although the application writes and reads that column, so follow-up periods and fields can fail to persist.
2. The generic dynamic-query path applies both the role scope and a separate authenticated-employee filter. This causes employee, admin, and super-admin operational queries to become self-only in many cases and prevents manager or organization access.
3. Attendance child queries contain the same kind of self-only contradiction, preventing subordinate or organization-wide access.
4. A named employee subject is not persisted across chat turns, so a follow-up after switching context can silently return to the authenticated employee.
5. The chat rate limiter counts every chat request as a failed attempt, allowing 120 chat requests to lock the authenticated employee out of chat.
6. Payroll named-subject queries can combine an own-row condition with a requested-subject condition and therefore fail to return a valid authorized row.
7. The model currently refuses to load unless CUDA is available, so the API will be functionally degraded on CPU-only deployments.

## 2. Overall Application Health

**Overall readiness: NOT READY**

The security model is stronger than a typical unrestricted SQL-generation implementation, but confirmed scope and context bugs prevent core multi-role behavior. Production readiness requires database migration verification, authorization fixes, follow-up-state verification, and runtime validation.

### Health summary

| Area | Assessment |
|---|---|
| Authentication | Partially ready |
| RBAC and data isolation | Deficient |
| Dynamic query safety | Strong validation, inconsistent scope |
| Model integration | Potentially fragile; GPU-dependent |
| Chat context | Defective in database persistence and subject switching |
| REST endpoints | Mostly secure for self-access |
| Error handling | Generally structured |
| Frontend integration | Not verified; no frontend source found |
| Runtime operations | Not verified |

## 3. Architecture and Execution Flow

The active chat flow is:

1. `POST /api/chat/{employee_code}` authenticates the bearer token and verifies active employee status.
2. The employee code is matched to the authenticated employee.
3. A chat security screen checks length and prompt-injection patterns.
4. The actor is loaded from PostgreSQL and its role/department/organization are placed in context.
5. A subject is resolved only for admin/super-admin actors.
6. The LangGraph supervisor selects greeting, compound, query, refusal, or clarification routing.
7. The planning or direct-answer path produces an approved operation.
8. Plan correction adds dates, fields, status filters, and context.
9. Entity and field authorization is checked.
10. `execute_query_plan` builds parameterized SQL and applies RLS context.
11. Response formatting and optional narration produce the result.
12. The result and follow-up operation metadata are cached and remembered.

Primary entry points:

- [backend/main.py](/d:/tickora-ai/backend/main.py): REST endpoints, chat endpoint, cache, session setup.
- [backend/agents/graph.py](/d:/tickora-ai/backend/agents/graph.py): LangGraph routing.
- [backend/agents/nodes.py](/d:/tickora-ai/backend/agents/nodes.py): supervisor, correction, execution, and compound nodes.
- [backend/services/llm_chat_service.py](/d:/tickora-ai/backend/services/llm_chat_service.py): planning, formatting, direct answers.
- [backend/services/dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py): allowlisted SQL generation.
- [backend/security/access_policy.py](/d:/tickora-ai/backend/security/access_policy.py): actor and scope policy.
- [backend/security/subject_resolution.py](/d:/tickora-ai/backend/security/subject_resolution.py): named-subject resolution.

## 4. Functional Coverage by Entity

| Entity | Registered operations | Audit assessment | Key limitations |
|---|---|---|---|
| Attendance | list, count, sum, group_by | PARTIAL | Admin/organization scope contradicted by generic/child self filters |
| Leave requests | list, count | PARTIAL | Generic scope is self-only for admins/super admins |
| Leave balances | list, count, sum, group_by | PARTIAL | Direct answer does not apply a resolved subject |
| Leave types | list, count | PASS for organization scope | Organization scoped |
| Holidays | list, count | PASS for organization scope | Regional/calendar behavior may require runtime verification |
| WFH requests | list, count | PARTIAL | Generic scope is self-only for admins/super admins |
| Timesheets | list, count | PARTIAL | Generic scope is self-only for admins/super admins |
| Work schedules | list | PARTIAL | Generic scope is self-only for admins/super admins |
| Tasks | list, count, sum, group_by | PARTIAL | Subject filters and scope need runtime verification |
| Payroll summaries | list | PARTIAL | Named-subject scope can become contradictory |
| Loan requests | list | PARTIAL | Subject-specific organization behavior needs runtime verification |
| Attendance punches | list, count | PARTIAL | Authenticated self filter conflicts with role scope |
| Attendance adjustments | list, count | PARTIAL | Authenticated self filter conflicts with role scope |
| Employee directory | direct fixed result | PARTIAL | Admin and super-admin only; employee scope and runtime output need verification |

## 5. RBAC and Data Isolation Findings

### F-001 — Generic operational queries overwrite role scope with a self filter

- **Severity:** CRITICAL
- **Category:** RBAC / Data isolation
- **Affected files/functions:** [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:1225), [access_policy.py](/d:/tickora-ai/backend/security/access_policy.py:141)
- **Classification:** CONFIRMED

**Technical explanation:** For `employee_id`, `employee_task`, and `employee_manager` scopes, the executor first adds `scope_clause` and then adds a second condition:

`owner_column(entity) = :self_employee_id`

This contradicts department and organization scope. Because the conditions are ANDed, an admin or super admin cannot retrieve subordinate or organization records for leave, WFH, timesheets, balances, schedules, or other generic entities. The same branch applies after scope resolution.

**Reproduction:** Authenticated admin asks for department leave requests. Scope clause permits department IDs, then the self filter restricts rows to the admin.

**Expected behavior:** Admin sees department data; super admin sees organization data; employee sees only own data.

**Actual behavior:** Admin/super-admin results are restricted to actor employee ID for generic entities.

**Impact:** Core role functionality is broken; may appear like missing data rather than leakage.

**Recommended correction:** Remove the separate self filter for roles whose `scope_clause` already expresses department or organization scope. Use one authoritative scope clause per entity.

### F-002 — Attendance child queries force actor ownership

- **Severity:** CRITICAL
- **Category:** RBAC / IDOR
- **Affected file/function:** [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:1020)
- **Classification:** CONFIRMED

**Technical explanation:** Attendance-punch and attendance-adjustment queries start with `attendance.employee_id = :authenticated_employee_id`, then append `scope_clause`. This makes employee-only behavior for all roles and contradicts admin/subordinate or super-admin organization access.

**Reproduction:** Admin asks for attendance punches from a subordinate.

**Expected behavior:** Admin sees permitted department punches.

**Actual behavior:** Query adds actor ID, returning no subordinate punches.

**Impact:** Authorized manager/super-admin child-record access is unreachable.

**Recommended correction:** Remove the unconditional authenticated-employee condition and rely on the ownership scope clause plus subject filter.

### F-003 — Named-subject context is not persisted across follow-ups

- **Severity:** HIGH
- **Category:** Session isolation / Context switching
- **Affected files/functions:** [chat_memory.py](/d:/tickora-ai/backend/services/chat_memory.py:25), [main.py](/d:/tickora-ai/backend/main.py:600), [subject_resolution.py](/d:/tickora-ai/backend/security/subject_resolution.py:38)
- **Classification:** CONFIRMED

**Technical explanation:** Follow-up memory stores only operation, period, and fields. It does not store `subject_id`. `resolve_subject` evaluates each current question independently. A follow-up containing no employee name or "my" does not retain the previous named employee.

**Reproduction:** Admin asks about EMP002 attendance; then asks "What about last month?"

**Expected behavior:** The second query continues EMP002 context if that context switching is product-supported.

**Actual behavior:** The subject resolves to none or the actor, and the second query is likely for the admin's own data.

**Impact:** Incorrect subject selection and potential confusing or unauthorized user assumptions. It does not expose another employee by itself, but it breaks intended context switching and may disclose actor data after a switch.

**Recommended correction:** Persist and validate subject state in the chat session, tied to employee/organization authorization, or disable named-subject follow-ups.

### F-004 — Generic entities do not apply resolved subject IDs

- **Severity:** HIGH
- **Category:** Manager access / Subject resolution
- **Affected file/function:** [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:1225)
- **Classification:** CONFIRMED

**Technical explanation:** The subject context is set before graph execution, but generic SQL only uses authenticated `employee_id`; it never adds a subject employee ID for named employee questions. Leave balances, leave requests, WFH, timesheets, work schedules, and attendance can therefore default to actor-owned rows.

**Reproduction:** Admin asks "Show EMP002's leave balance."

**Expected behavior:** If EMP002 is authorized, return EMP002's balance.

**Actual behavior:** Generic/leave-balance execution remains actor-scoped and should not switch to EMP002.

**Impact:** Manager access to valid subordinates is incompletely implemented.

**Recommended correction:** Add a validated subject filter as a replacement for the actor self filter only when the subject is within the role's scope.

### F-005 — Payroll named-subject scope can conflict

- **Severity:** HIGH
- **Category:** Payroll / Subject authorization
- **Affected files/functions:** [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:300), [llm_chat_service.py](/d:/tickora-ai/backend/services/llm_chat_service.py:1158)
- **Classification:** CONFIRMED

**Technical explanation:** Payroll query execution adds actor employee ID for every non-super-admin or non-`org` plan and additionally adds subject employee ID when a subject is resolved. A super admin asking "EMP002 payroll" may be given `scope=own`, producing both `ps.employee_id = actor` and `ps.employee_id = EMP002`.

**Reproduction:** Super admin asks payroll for employee EMP002 without organization/team wording.

**Expected behavior:** Authorized super-admin query should target EMP002 within the organization.

**Actual behavior:** It can require both IDs and return no row.

**Impact:** Authorized payroll access fails; implementation may vary because subject and plan scope depend on wording.

**Recommended correction:** Normalize named subject to organization scope and apply exactly one subject/actor condition.

## 6. Authentication and Security Findings

### F-006 — Chat limiter counts successful chat requests as failures

- **Severity:** MEDIUM
- **Category:** Availability / Rate limiting
- **Affected file/function:** [main.py](/d:/tickora-ai/backend/main.py:602), [login_rate_limiter.py](/d:/tickora-ai/backend/services/login_rate_limiter.py:42)
- **Classification:** CONFIRMED

**Technical explanation:** `chat_limiter.hit(chat:<employee>)` invokes `record_failure` for every chat call, not just failures. The in-memory limiter raises once the chat key reaches the configured 120-request window.

**Reproduction:** Send 121 chat requests in one minute for the same employee.

**Expected behavior:** Chat should use a separate request-rate policy or count actual failures only.

**Actual behavior:** The employee receives HTTP 429 after the window fills, even with successful chats.

**Impact:** Availability degradation and inconsistent behavior across process workers.

**Recommended correction:** Implement a true request quota for chat or count failed chat/inference attempts only.

### F-007 — Login success does not reset the IP failure bucket

- **Severity:** LOW
- **Category:** Brute-force protection
- **Affected file/function:** [main.py](/d:/tickora-ai/backend/main.py:252)
- **Classification:** CONFIRMED

**Technical explanation:** A successful login resets the email key only. IP failure history remains until its 60-second window expires.

**Reproduction:** Several failures on one IP, followed by a successful login from that IP.

**Expected behavior:** Successful authentication may reset relevant failure counters.

**Actual behavior:** The IP counter remains for the existing window.

**Impact:** Lower availability and false lockout risk.

**Recommended correction:** Reset both email and IP buckets after a successful login, with care to prevent attackers from resetting shared-IP counters.

### F-008 — JWT validation is correctly strict but employee-code identity is ignored

- **Severity:** INFO
- **Category:** Authentication
- **Affected files/functions:** [auth_service.py](/d:/tickora-ai/backend/services/auth_service.py:52), [auth.py](/d:/tickora-ai/backend/dependencies/auth.py:10)
- **Classification:** CONFIRMED

**Technical explanation:** JWTs require `sub`, `exp`, and `iat`, use HS256, and expiration is validated. Authentication loads the active employee by the numeric subject and ignores the employee-code claim. This is appropriate because the database employee record is authoritative.

**Impact:** Low residual risk, provided the secret remains strong and is not committed or reused.

**Recommended correction:** Continue to verify `sub` against active database identity and rotate the secret if exposure is suspected.

### F-009 — CORS and metrics exposure require deployment verification

- **Severity:** MEDIUM
- **Category:** API security / Deployment
- **Affected files/functions:** [main.py](/d:/tickora-ai/backend/main.py:132), [main.py](/d:/tickora-ai/backend/main.py:138)
- **Classification:** POTENTIAL

**Technical explanation:** CORS credentials, all methods, and all headers are enabled, with origins supplied by configuration. `/metrics` is mounted without application authentication.

**Impact:** Incorrect origins or accidental Prometheus exposure may increase attack surface or reveal operational metadata.

**Recommended correction:** Restrict origins and headers in production, and protect or isolate the metrics endpoint as appropriate.

## 7. LLM and Model Quality Findings

### F-010 — Model requires CUDA and can leave chat unavailable

- **Severity:** HIGH
- **Category:** Model reliability / Deployment
- **Affected file/function:** [model_inference.py](/d:/tickora-ai/backend/services/model_inference.py:228)
- **Classification:** CONFIRMED

**Technical explanation:** `load_model` explicitly raises unless CUDA is available and requires an NVIDIA/GPU inference environment. Startup catches loading failure and continues, but chat model-dependent operations remain unavailable.

**Reproduction:** Deploy on CPU-only infrastructure or a host with no CUDA.

**Expected behavior:** Deployment should define supported hardware and fail or degrade explicitly.

**Actual behavior:** The API starts, health reports not ready, and chat inference is unavailable.

**Impact:** Deployment portability and availability risk.

**Recommended correction:** Support an explicit CPU mode or deployment-time GPU validation and document capacity requirements.

### F-011 — Process-local plan and answer caches are not multi-worker safe

- **Severity:** MEDIUM
- **Category:** Performance / Cache correctness
- **Affected file/function:** [answer_cache.py](/d:/tickora-ai/backend/services/answer_cache.py:10)
- **Classification:** CONFIRMED

**Technical explanation:** Both plan and answer caches are process-local memory dictionaries. Worker-to-worker hits vary and the cache can consume up to configured entries per process.

**Impact:** Inconsistent cache behavior and no shared invalidation across workers.

**Recommended correction:** Use Redis or another shared cache for multiple workers, with tenant/employee/RBAC-aware keys.

### F-012 — Schema metadata cache has no explicit invalidation

- **Severity:** MEDIUM
- **Category:** Schema reliability
- **Affected file/function:** [schema_catalog.py](/d:/tickora-ai/backend/services/schema_catalog.py:34)
- **Classification:** CONFIRMED

**Technical explanation:** `discover_schema` is LRU-cached for eight entries, but no production invalidation is implemented. Schema/operation changes may leave registry metadata stale until process restart.

**Impact:** Queries may disappear or remain from stale metadata after migrations.

**Recommended correction:** Key discovery by schema plus migration/version fingerprint and invalidate explicitly after migrations.

### F-013 — Date resolution may mishandle contradictory ranges

- **Severity:** MEDIUM
- **Category:** Date parsing
- **Affected file/function:** [date_resolver.py](/d:/tickora-ai/backend/services/date_resolver.py:186)
- **Classification:** POTENTIAL

**Technical explanation:** `_ordered_or_none` rejects inverted ranges, but later fallback patterns can match individual month/date components and potentially return a valid but unintended period.

**Reproduction:** Ask for a range whose named start period is after the named end period.

**Expected behavior:** Ask for clarification or return an invalid-date/range error.

**Actual behavior:** Fallback date interpretation must be runtime-verified.

**Impact:** Incorrect answer periods or contradictory filters.

**Recommended correction:** Detect explicit contradictory ranges before fallback matching and return a validation error.

## 8. Realistic User Scenario Evaluation

| Scenario | Expected Behavior | Audit Result | Status | Evidence |
|---|---|---|---|---|
| What is my attendance today? | Self-only attendance row | Employee route can work if model/date logic succeeds | NOT VERIFIED | [llm_chat_service.py](/d:/tickora-ai/backend/services/llm_chat_service.py:3713), [date_resolver.py](/d:/tickora-ai/backend/services/date_resolver.py:186) |
| Show my attendance this month | Self-only monthly attendance | Generic/employee scope correct for employee | NOT VERIFIED | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:1225) |
| What is my leave balance? | Direct own balance | Direct path present, but session/RBAC runtime unverified | PARTIAL | [llm_chat_service.py](/d:/tickora-ai/backend/services/llm_chat_service.py:3188) |
| Show my pending leave requests | Employee-owned pending requests | Generic scope should protect employee; admin manager scope broken | PARTIAL | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:1225) |
| Upcoming holidays | Organization holidays | Organization calendar join and RLS are in place | NOT VERIFIED | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:449) |
| My payroll summary | Actor-owned payroll | Employee scope direct SQL present | PARTIAL | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:300) |
| My assigned tasks | Actor-owned tasks | Task SQL is implemented but filters/scope need runtime verification | NOT VERIFIED | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:580) |
| Yesterday/last week/previous month | Deterministic date resolution | Date resolver covers these patterns | NOT VERIFIED | [date_resolver.py](/d:/tickora-ai/backend/services/date_resolver.py:186) |
| Attendance between dates | One bounded range | Range parsing and query validation present | NOT VERIFIED | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:1280) |
| How many absent days? | Attendance count and absent status | Count normalization present | NOT VERIFIED | [llm_chat_service.py](/d:/tickora-ai/backend/services/llm_chat_service.py:650) |
| How many leave requests approved? | Count with status filter | Status/date handling present | NOT VERIFIED | [llm_chat_service.py](/d:/tickora-ai/backend/services/llm_chat_service.py:650) |
| Show pending tasks | Self/task scope plus pending status | Task SQL supports status; generic task scope present | NOT VERIFIED | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:580) |
| Attendance grouped by month | Grouped monthly attendance | Group-by implementation present | NOT VERIFIED | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:1400) |
| Highest-priority tasks | Status/priority representation unknown | No priority field in registered task list | FAIL | [operation_registry.py](/d:/tickora-ai/backend/services/operation_registry.py:126) |
| Colleague attendance | Admin/super allowed; employee refused | Employee refusal, manager access blocked by scope bug | FAIL | [subject_resolution.py](/d:/tickora-ai/backend/security/subject_resolution.py:38) |
| EMP002 payroll | Authorized role can request named subject | Potential contradictory own/subject conditions | FAIL | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:300) |
| Team pending leave requests | Admin department/super organization | Scope bug prevents expected manager access | FAIL | [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:1225) |
| Unauthorized manager-level access | Refuse employee | Employee role entity denial and third-party refusal | PASS for code path | [nodes.py](/d:/tickora-ai/backend/agents/nodes.py:399) |
| What about last month? | Reuse period and subject context | Period persistence intended but subject lost and migration is defective | FAIL | [chat_memory.py](/d:/tickora-ai/backend/services/chat_memory.py:25) |
| Show only approved ones | Reuse prior operation and status | Status and follow-up period code exists | PARTIAL | [llm_chat_service.py](/d:/tickora-ai/backend/services/llm_chat_service.py:650) |
| Give me the total | Reuse operation or clarify | Follow-up detection may preserve operation | PARTIAL | [nodes.py](/d:/tickora-ai/backend/agents/nodes.py:302) |
| Switch context / follow-up | Persist authorized subject | Subject switching not persisted | FAIL | [main.py](/d:/tickora-ai/backend/main.py:600) |
| Invalid date | Deterministic validation message | Code maps invalid dates to clarification | PARTIAL | [nodes.py](/d:/tickora-ai/backend/agents/nodes.py:421) |
| Unknown employee | Generic not-found message | Subject resolver should return generic message | NOT VERIFIED | [subject_resolution.py](/d:/tickora-ai/backend/security/subject_resolution.py:62) |
| Unsupported entity | Unsupported/refusal response | Supervisor and planner allowlist protect request | NOT VERIFIED | [nodes.py](/d:/tickora-ai/backend/agents/nodes.py:313) |
| Contradictory date filters | Reject or clarify | Potential fallback interpretation issue | PARTIAL | [date_resolver.py](/d:/tickora-ai/backend/327) |
| Empty question | Pydantic 422 | `min_length=1` enforced | PASS for code path | [main.py](/d:/tickora-ai/backend/main.py:195) |
| Extremely long input | 422 or security-screen refusal | Pydantic allows 1000; screen limits 500 | PARTIAL | [main.py](/d:/tickora-ai/backend/main.py:195), [input_screen.py](/d:/tickora-ai/backend/security/input_screen.py:34) |
| Unrelated question | Out-of-scope refusal | Supervisor is designed to refuse | NOT VERIFIED | [nodes.py](/d:/tickora-ai/backend/agents/nodes.py:313) |

## 9. Validation and Error Handling Findings

### F-014 — Structured chat-session migration is incomplete

- **Severity:** CRITICAL
- **Category:** Database migration / Follow-up context
- **Affected files/functions:** [20261107_chat_sessions.py](/d:/tickora-ai/alembic/versions/20261107_chat_sessions.py:12), [chat_memory.py](/d:/tickora-ai/backend/services/chat_memory.py:32)
- **Classification:** CONFIRMED

**Technical explanation:** The migration creates `chat_sessions` with `employee_id`, `session_id`, `last_topic`, `last_active`, but no `last_plan`. The application executes `INSERT ... last_plan` and `SELECT last_plan`. PostgreSQL will reject these statements if the migration has been applied as written.

**Reproduction:** Apply the migration, then complete a chat result that invokes `_remember_operation`.

**Expected behavior:** Session context writes and reads succeed.

**Actual behavior:** SQLAlchemy raises undefined-column error; `_remember_operation` catches and logs but no structured context is retained.

**Impact:** All period/field follow-ups are unreliable or unavailable.

**Recommended correction:** Add `last_plan` as JSONB in the migration or an immediate follow-up migration. Verify no old databases require a manual ALTER.

### F-015 — API chat errors are often normalized to HTTP 200

- **Severity:** MEDIUM
- **Category:** API contracts
- **Affected file/function:** [main.py](/d:/tickora-ai/backend/main.py:705)
- **Classification:** CONFIRMED

**Technical explanation:** `_chat` catches graph/model pipeline exceptions and returns `_text_result` dictionaries; the endpoint does not change HTTP status. Model unavailable, SQL failure, and unexpected pipeline failure can therefore be HTTP 200 with `intent=unavailable` or `unsupported`.

**Impact:** Frontend loading/error handling may depend on HTTP status and fail to distinguish operational failures.

**Recommended correction:** Reserve success HTTP 200 for valid results and use 503/500 or structured status codes for infrastructure failures.

### F-016 — Query validation is strong and parameterized

- **Severity:** INFO
- **Category:** SQL injection / Validation
- **Affected file/function:** [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:47)
- **Classification:** CONFIRMED

**Technical explanation:** Operation IDs come from an explicit registry, identifiers are quoted, filter values are bound as SQLAlchemy parameters, and date/filter types are validated. The schema argument is constrained by a strict regex.

**Impact:** Low risk of direct SQL injection in dynamic chat queries.

**Recommended correction:** Preserve strict registry validation and add operation-specific Pydantic plans if the schema grows.

### F-017 — Validation response may expose Pydantic field details

- **Severity:** LOW
- **Category:** Error handling
- **Affected file/function:** [errors.py](/d:/tickora-ai/backend/errors.py:63)
- **Classification:** CONFIRMED

**Technical explanation:** Request-validation errors include Pydantic `exc.errors()` in the structured `details` field.

**Impact:** Usually safe, but can expose Python type/input names rather than a fully normalized user-facing message.

**Recommended correction:** Return a stable code and redact internal field locations in public deployments.

## 10. Performance and Reliability Findings

### F-018 — Model generation has serialization and queue limits but no CPU fallback

- **Severity:** MEDIUM
- **Category:** Concurrency / Reliability
- **Affected file/function:** [model_inference.py](/d:/tickora-ai/backend/services/model_inference.py:36)
- **Classification:** CONFIRMED

**Technical explanation:** Generation is correctly serialized to one slot, with 5-second queue wait and 30-second generation max. However queue/format failures do not provide a fallback answer for most model-dependent questions.

**Impact:** Contention may return 503 or unavailable; CPU deployments cannot load the model.

**Recommended correction:** Define supported fallback behavior, use warm capacity alerts, and expose queue saturation metrics.

### F-019 — Schema discovery queries metadata with the owner engine

- **Severity:** LOW
- **Category:** Database privileges
- **Affected file/function:** [schema_catalog.py](/d:/tickora-ai/backend/services/schema_catalog.py:34)
- **Classification:** CONFIRMED

**Technical explanation:** The catalog uses `backend.db.engine`, while query execution uses `agent_engine` with RLS. Metadata discovery therefore depends on owner privileges and runs independently of the actor.

**Impact:** Schema errors or privilege changes can affect startup; sensitive table/column filtering is token-based but allowlisted operations limit exposure.

**Recommended correction:** Use a least-privilege catalog connection or cache trusted catalog metadata outside request execution.

### F-020 — N+1 and large-result risk is limited but not fully bounded

- **Severity:** LOW
- **Category:** Performance
- **Affected files/functions:** [dynamic_query_service.py](/d:/tickora-ai/backend/services/dynamic_query_service.py:47), [llm_chat_service.py](/d:/tickora-ai/backend/services/llm_chat_service.py:3713)
- **Classification:** CONFIRMED

**Technical explanation:** Dynamic queries have a maximum of 100 and team summaries add one sentinel row, but some formatting functions perform follow-up database lookups or employee-name lookups. List and count paths are generally bounded.

**Impact:** Low to medium at scale, especially with repeated narration and cache misses.

**Recommended correction:** Add database statement timeouts, query metrics, and bounded response payload validation.

## 11. Frontend-Backend Integration Findings

No frontend source was found in the workspace snapshot. No React API integration files were available for review.

### F-021 — Frontend response contract is backend-only and partially inconsistent

- **Severity:** MEDIUM
- **Category:** Frontend-backend contract
- **Affected file/function:** [main.py](/d:/tickora-ai/backend/main.py:705)
- **Classification:** POTENTIAL

**Technical explanation:** Chat success and refusal responses share HTTP 200 and vary intent/message fields. REST endpoints use normal HTTP codes and structured errors, while chat operational failures are embedded in the response body.

**Impact:** Frontend must inspect `intent`, `success`, and `answer/message` rather than status codes.

**Recommended correction:** Publish one versioned chat response schema and consistent HTTP semantics.

## 12. Missing or Incomplete Implementations

1. Priority information is not registered for tasks; "highest-priority tasks" has no supported priority field.
2. Employee directory and team behavior is direct-code only, not a complete model/registry flow.
3. Subject persistence is absent from chat context.
4. Redis/shared cache is absent.
5. CPU model support is absent.
6. The `last_plan` migration is missing.
7. Shared cache invalidation is absent.
8. Named-subject payroll scope normalization is incomplete.
9. The generic scope and subject filter implementation does not support all documented manager scenarios.
10. Frontend source/loading behavior was unavailable for audit.

## 13. Critical Bugs and Potential Failure Points

### Confirmed

- Missing `last_plan` database column breaks follow-up state persistence.
- Generic scope clauses are combined with a self filter, preventing manager/organization access.
- Attendance child scope is combined with a self filter.
- Subject switching is not persisted.
- Chat limiter counts successful requests.
- Named payroll subject scope can conflict.

### Potential

- CUDA-only deployment.
- Multi-worker cache inconsistency.
- Contradictory date-range fallback.
- Stale schema catalog.
- Prometheus or CORS exposure.

### Unverified

- Actual migration state.
- Live RLS policy behavior.
- GPU/model accuracy and latency.
- Database indexes and execution plans.
- Frontend response handling.
- Live role data behavior.

## 14. Prioritized Recommendations

1. Add and verify the `chat_sessions.last_plan` column, then test session period/field persistence.
2. Correct generic query scope logic: choose one scope clause and one subject filter, never combine contradictory employee restrictions.
3. Fix attendance-punch/adjustment scope filters.
4. Persist and revalidate named subjects in session context.
5. Fix payroll subject/scope normalization.
6. Replace chat-limiter success counting with an actual request/failure policy.
7. Add CPU model support or enforce and monitor GPU-only deployment.
8. Implement shared cache and explicit schema/catalog invalidation.
9. Standardize chat HTTP and response contracts.
10. Add live database and role-scenario verification.

### Security Findings Summary

| Finding | Severity | Classification | Status |
|---|---|---:|---|
| Generic scope plus self filter | CRITICAL | CONFIRMED | Open |
| Attendance child self filter | CRITICAL | CONFIRMED | Open |
| Missing subject persistence | HIGH | CONFIRMED | Open |
| Payroll subject scope conflict | HIGH | CONFIRMED | Open |
| Subject not applied to generic entities | HIGH | CONFIRMED | Open |
| Chat limiter availability bug | MEDIUM | CONFIRMED | Open |
| CORS/metrics exposure | MEDIUM | POTENTIAL | Requires verification |
| JWT | INFO | CONFIRMED | Proper implementation with secret controls |

## 15. Final Production Readiness Assessment

**Overall application readiness: NOT READY**

### Top 10 issues requiring attention

1. Add and apply `chat_sessions.last_plan`.
2. Fix generic dynamic-query scope.
3. Fix attendance child scope.
4. Persist validated subject context.
5. Fix named payroll scope.
6. Fix chat rate limiting.
7. Resolve manager access in generic entities.
8. Add CPU or deployment-capacity support.
9. Add shared cache/invalidation.
10. Verify live RLS and frontend contracts.

### Recommended remediation order

1. Database migration and chat context
2. RBAC/scope clause and subject propagation
3. Payroll/task/loan edge validation
4. JWT and login/chat rate limiting
5. Cache and schema invalidation
6. Model deployment and fallback
7. Frontend contract and runtime verification

### Areas requiring manual runtime verification

- Migrations already applied to the target database
- RLS behavior under owner and agent connections
- Realistic questions for every role
- Payroll named-subject behavior
- Manager department and super-admin organization behavior
- Context switch and follow-up behavior
- CUDA, VRAM, latency, queue wait, and model warm-up
- Database query plans and result limits
- Multi-worker deployment and cache consistency
- Frontend loading, error, and empty-data handling
- CORS origins and metrics endpoint exposure
