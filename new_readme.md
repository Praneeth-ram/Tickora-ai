# Tickora AI — Multi-Tenant Intelligent Attendance Chatbot

## 1. Project Overview

Tickora AI is an AI-powered chatbot integrated into the Tickora attendance management application. It enables employees to ask natural-language questions about attendance, leave requests, work-from-home requests, timesheets, holidays, and work schedules.

The chatbot uses a **hybrid architecture combining a fine-tuned language model, dynamic database schema discovery, an approved operation registry, and PostgreSQL query execution**.

The model interprets user questions and generates structured query plans. The backend validates those plans, enforces tenant and user permissions, retrieves information from PostgreSQL, and generates answers grounded in actual query results.

### Primary objective

Build a multi-tenant chatbot that:

- Understands natural-language questions.
- Retrieves actual information from PostgreSQL.
- Works across multiple organizations using a shared model.
- Supports newly provisioned tenants without retraining for each tenant.
- Discovers tenant database metadata dynamically.
- Supports approved operations without requiring a fixed neural-network output class for every database table.
- Enforces strict tenant isolation and employee-level authorization.
- Supports model improvement through reviewed training examples.
- Integrates with the existing FastAPI backend and React frontend.

### Important architectural principle

**The model decides what the user is asking for. The backend decides what the user is allowed to access and executes the operation.**

The model must never independently select the tenant, override the authenticated employee identity, access arbitrary tables, or execute unrestricted generated SQL.

---

## 2. Existing Technology Stack

Use the existing project configuration as the source of truth. The intended stack is:

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
| Testing | pytest and existing project test tools |

Do not replace working components or introduce a new framework without first inspecting the repository and establishing a clear need.

---

## 3. Current Project Context and Known Schema

The project has previously included a FastAPI/PostgreSQL prototype, attendance-related endpoints, a small seven-intent classifier, and an initial custom Transformer intent model.

The initial intent categories were:

- `attendance_records`
- `attendance_summary`
- `holiday_lookup`
- `leave_status`
- `schedule_lookup`
- `timesheet_lookup`
- `wfh_status`

These categories describe the initial classifier, not the final operation architecture. The new architecture should use logical operations and validated query plans rather than relying exclusively on a fixed classifier output layer.

### Known tenant database structures

The tenant SQL design has referenced the following tables:

| Table | Business purpose |
|---|---|
| `user_account` | Employee accounts and organization-specific user information |
| `attendance_day` | Daily attendance summaries |
| `attendance_punch` | Individual attendance punch events |
| `leave_request` | Leave requests |
| `user_leave_balance` | Leave balance information |
| Leave approval/request-day tables | Leave workflow and date details |
| `wfh_request` | Work-from-home requests |
| WFH approval tables | WFH approval workflow |
| Work schedule master/day-rule/user-mapping tables | Employee schedules and working-time rules |
| Holiday tables and mappings | Organization-specific holidays |

The shared/public schema has previously referenced:

- `public.organization`
- `public.user_global`

The organization registry includes organization identifiers and tenant schema mapping information.

**Important:** These names and relationships must be verified against the actual repository migrations and database. Do not assume that every listed table exists in every schema or that illustrative column names are correct.

The existing prototype has also used names such as `employees` and `attendance_records`. These do not necessarily match the tenant schema. Resolve this mismatch before implementing production query execution.

---

## 4. Target Architecture

The target request pipeline is:

1. React submits a chat message.
2. FastAPI authenticates the request.
3. The backend resolves the authenticated user and organization.
4. The tenant resolver selects the authorized database/schema.
5. The model generates a structured query plan.
6. The schema catalog provides metadata for the selected tenant.
7. The operation registry identifies permitted operations.
8. The query validator checks the plan against the registry, schema, and permissions.
9. The query execution service executes a parameterized query.
10. The response service generates an answer from the actual result.
11. FastAPI returns a structured response to React.

### Logical architecture

```text
React Chat UI
     |
     v
FastAPI Chat Endpoint
     |
     +---- Authentication and Authorization
     |
     +---- Tenant Resolver
     |          |
     |          v
     |     Organization Registry
     |
     +---- Fine-Tuned Model
     |          |
     |          v
     |     Structured Query Plan
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

This is a logical component diagram. The components may initially be implemented as modules within the existing FastAPI application.

---

## 5. Multi-Tenant Database Architecture

### 5.1 Intended tenancy model

The current design suggests a PostgreSQL schema-per-tenant architecture.

Example:

```text
tickora_db/
├── public/
│   ├── organization
│   └── user_global
│
├── tenant_abc/
│   ├── user_account
│   ├── attendance_day
│   ├── attendance_punch
│   ├── leave_request
│   └── wfh_request
│
└── tenant_xyz/
    ├── user_account
    ├── attendance_day
    ├── attendance_punch
    ├── leave_request
    └── wfh_request
```

The tenant schemas should be created from the same versioned migration set.

If the repository instead uses separate databases per tenant, adapt the tenant resolver to select the appropriate database connection. Do not implement both tenancy models simultaneously without a requirement.

### 5.2 Tenant provisioning

When a new organization registers:

1. Create its organization record.
2. Generate a safe, unique schema name on the backend.
3. Create the tenant schema.
4. Apply the approved tenant migrations.
5. Register the schema against the organization ID.
6. Create or invite the organization administrator.
7. Verify the tenant schema.
8. Mark the organization active after successful provisioning.

Provisioning should be retry-safe and should not leave a tenant marked active when initialization fails.

### 5.3 Tenant resolution

For every chat request:

1. Validate the existing authentication credentials.
2. Resolve the authenticated user from trusted server-side identity.
3. Resolve the organization membership.
4. Fetch the tenant configuration from the organization registry.
5. Verify that the user is active and authorized for that organization.
6. Use the resolved tenant context throughout the request.

Never trust organization IDs, schema names, or employee IDs supplied by the model or chat message.

If users can belong to multiple organizations, verify their membership in the organization selected for the current request.

### 5.4 Tenant security

- Do not allow users to select arbitrary schemas.
- Do not accept a schema name from model output.
- Use safely quoted, trusted database identifiers.
- Prefer explicit schema-qualified table references.
- If using PostgreSQL `search_path`, manage it safely for each transaction/connection and reset it before reuse.
- Use least-privilege database credentials.
- Consider PostgreSQL row-level security as defense in depth.
- Test cross-tenant access attempts explicitly.

---

## 6. Dynamic Schema Catalog

### Purpose

The schema catalog discovers the database metadata available for a tenant.

Create or adapt:

`backend/services/schema_catalog.py`

The catalog should inspect:

- Table names.
- Column names and types.
- Primary keys.
- Foreign keys.
- Relationships.
- Nullable columns.
- Approved views.

Use SQLAlchemy inspection against the tenant's trusted engine or connection.

### Example metadata

```json
{
  "tenant_id": "org_101",
  "schema_version": 4,
  "tables": {
    "attendance_day": {
      "columns": {
        "user_id": "BIGINT",
        "attendance_date": "DATE",
        "status": "VARCHAR",
        "regular_minutes": "INTEGER"
      }
    }
  }
}
```

This is illustrative metadata. Inspect the actual schema before relying on any field.

### Expected behavior

1. Resolve the tenant.
2. Inspect its schema.
3. Normalize the metadata.
4. Cache metadata with a tenant-specific cache key.
5. Refresh or invalidate the cache after migrations.
6. Expose only relevant metadata to the operation-planning layer.

Cache invalidation must be explicit. Do not assume that metadata remains valid after a tenant migration.

### Security requirements

Schema discovery does not authorize access to a table.

Do not automatically expose sensitive tables, credentials, internal metadata, audit logs, payroll, or unrelated administrative data merely because the inspector discovers them.

---

## 7. Operation Registry

### Purpose

The schema catalog describes what exists. The operation registry defines which business operations the chatbot may execute.

Create or adapt:

`backend/services/operation_registry.py`

An operation definition should specify:

- Logical operation ID.
- Underlying table, view, or approved query.
- Allowed fields.
- Allowed filters.
- Supported joins.
- User or role scope.
- Aggregations and business rules.
- Maximum result count.
- Read/write classification.
- Required permissions.
- Required schema capabilities.

### Initial logical operations

| Operation ID | Purpose |
|---|---|
| `attendance.list` | Retrieve attendance records |
| `attendance.count` | Count qualifying attendance days |
| `attendance.summary` | Calculate an approved attendance summary |
| `leave_request.list` | Retrieve leave requests |
| `wfh_request.list` | Retrieve WFH requests |
| `holiday.list` | Retrieve applicable holidays |
| `schedule.get` | Retrieve an assigned work schedule |
| `timesheet.summary` | Calculate an approved timesheet summary |

These IDs are proposed logical names. Reconcile them with existing APIs, actual database fields, and the final model output schema.

### Example registry definition

```python
OPERATION_REGISTRY = {
    "attendance.count": {
        "entity": "attendance_day",
        "allowed_fields": [],
        "allowed_filters": [
            "period",
            "start_date",
            "end_date",
            "status",
        ],
        "scope": "current_user",
        "aggregation": "count",
        "read_only": True,
    }
}
```

This is an illustrative starting point. It does not include the complete validation, query mapping, authorization, or SQL generation logic required for production.

### Dynamic behavior

For a new tenant using the standard schema, reuse the existing approved operations.

For a new column or changed relationship, refresh metadata and validate the existing mapping.

For a new business feature, discover its schema and explicitly define, review, implement, test, and authorize its operations.

**Never automatically authorize every discovered table or column.**

---

## 8. Structured Query Plan

The fine-tuned model should produce a structured query plan instead of executable SQL.

Example user message:

```text
How many days was I present this month?
```

Expected plan:

```json
{
  "operation": "attendance.count",
  "filters": {
    "period": "this_month",
    "status": "present"
  },
  "fields": [],
  "needs_clarification": false
}
```

The plan expresses user intent. It does not contain authoritative tenant identity, employee identity, database credentials, or a schema name.

### Query-plan contract

The backend should validate:

- Operation ID.
- Allowed fields.
- Allowed filters.
- Filter data types.
- Date formats and ranges.
- Aggregation rules.
- Clarification state.
- Maximum result limits.
- Schema compatibility.

Use Pydantic or an equivalent strict schema validator.

Reject unknown fields, unsupported operations, malformed filters, invalid dates, and unauthorized requests.

The validator must check operation-specific rules, not merely whether the output is valid JSON.

### Clarification example

User:

```text
Show my attendance.
```

Possible plan:

```json
{
  "operation": null,
  "filters": {},
  "fields": [],
  "needs_clarification": true,
  "clarification_question": "What date or date range would you like to check?"
}
```

If the backend can safely apply a defined default period, it may do so instead. The behavior must be consistent with product requirements.

---

## 9. Query Execution Service

Create or adapt:

`backend/services/dynamic_query_service.py`

The service should:

1. Accept a validated query plan and trusted tenant/user context.
2. Resolve the operation through the registry.
3. Verify schema compatibility.
4. Apply the authenticated user's scope.
5. Normalize date filters.
6. Build the approved SQLAlchemy query.
7. Bind filter values as parameters.
8. Enforce timeouts and result limits.
9. Execute with appropriate database privileges.
10. Return normalized results.

### Example query

Assume the actual tenant table supports the following columns:

- `user_id`
- `attendance_date`
- `status`

A logical query might be:

```sql
SELECT COUNT(*)
FROM tenant_abc.attendance_day
WHERE user_id = :authenticated_user_id
  AND attendance_date >= :start_date
  AND attendance_date < :end_date
  AND status = :status;
```

Parameters:

```python
{
    "authenticated_user_id": 501,
    "start_date": "2026-10-01",
    "end_date": "2026-11-01",
    "status": "present",
}
```

This is an example, not a verified query against the current database.

The tenant identifier must come from the tenant resolver. The employee ID must come from authentication. Dates and status must come from validated, normalized filters.

Use SQLAlchemy Core or another carefully controlled query-building approach. Do not concatenate user-provided text into SQL.

### Business rules

Implement and test the actual definitions of:

- Present and absent days.
- Half-days.
- Paid and unpaid days.
- Leave and holiday treatment.
- Regular working minutes.
- Overtime.
- Duplicate or corrected attendance records.

Do not assume that counting rows always gives the correct business answer.

---

## 10. Fine-Tuning Dataset

The model learns to convert natural-language questions into the approved query-plan format.

It should not learn tenant credentials, actual employee records, or organization-specific identifiers.

### JSONL structure

Each line is an independent training conversation.

```jsonl
{"messages":[{"role":"user","content":"Show my attendance today."},{"role":"assistant","content":"{\"operation\":\"attendance.list\",\"filters\":{\"period\":\"today\"},\"fields\":[\"attendance_date\",\"status\",\"first_in\",\"last_out\"],\"needs_clarification\":false}"}]}
{"messages":[{"role":"user","content":"How many days was I present this month?"},{"role":"assistant","content":"{\"operation\":\"attendance.count\",\"filters\":{\"period\":\"this_month\",\"status\":\"present\"},\"fields\":[],\"needs_clarification\":false}"}]}
{"messages":[{"role":"user","content":"Show my rejected leave requests."},{"role":"assistant","content":"{\"operation\":\"leave_request.list\",\"filters\":{\"status\":\"rejected\"},\"fields\":[\"start_date\",\"end_date\",\"status\"],\"needs_clarification\":false}"}]}
```

These are illustrative examples. The output must match the final query-plan contract and operation registry exactly.

### Dataset sources

Use a combination of:

1. Synthetic examples derived from approved operation definitions.
2. Reviewed, anonymized employee questions.
3. Edge cases, ambiguous questions, and security test prompts.

### Dataset coverage

Include:

- Attendance retrieval and summaries.
- Date ranges and relative dates.
- Leave status and date filters.
- WFH requests.
- Holidays.
- Work schedules.
- Timesheets and overtime.
- Clarification requests.
- Unsupported operations.
- Malformed or contradictory requests.
- Attempts to bypass tenant and user authorization.

### Dataset validation

Before training:

- Validate JSONL syntax.
- Validate the message format.
- Validate every assistant query plan.
- Check that operation IDs exist.
- Check fields and filters against the registry.
- Remove sensitive information.
- Split data by scenario/template group to prevent near-duplicate leakage.
- Record the dataset version.

Start with a small reviewed pilot and grow the dataset based on evaluation results. A handful of examples is useful for learning the format but is not enough for reliable production behavior.

---

## 11. Model Training and Evaluation

Use Google Colab for the initial fine-tuning experiment.

A compatible Hugging Face instruction-tuned model can be adapted with supervised fine-tuning and PEFT/LoRA or QLoRA.

A Qwen-family model may be evaluated as an initial candidate, subject to current license terms, hardware, model compatibility, and project requirements.

### Training workflow

1. Load and validate the JSONL dataset.
2. Load the base model and tokenizer.
3. Apply the model's correct chat template.
4. Prepare the dataset for supervised fine-tuning.
5. Establish baseline metrics before training.
6. Fine-tune the model.
7. Evaluate against a held-out dataset.
8. Save the adapter and configuration.
9. Record model, dataset, and training versions.
10. Deploy only after evaluation and security testing.

### Evaluation metrics

Measure:

- JSON parse success rate.
- Exact operation accuracy.
- Filter extraction accuracy.
- Date interpretation accuracy.
- Clarification accuracy.
- Unsupported-operation handling.
- Unauthorized-request handling.
- End-to-end query correctness.

Low training loss alone does not demonstrate reliable query planning.

### Training data must match production

The training output format, operation IDs, fields, filters, and clarification schema must match the deployed backend.

If the query-plan contract changes, update the dataset and tests accordingly. Fine-tuning should be driven by measured model limitations, not automatically triggered whenever a tenant is added.

---

## 12. FastAPI Integration

Create or adapt the following modules, preserving the existing project structure where appropriate:

```text
backend/
├── api/
│   └── chat.py
├── services/
│   ├── tenant_resolver.py
│   ├── schema_catalog.py
│   ├── operation_registry.py
│   ├── query_plan_schema.py
│   ├── query_validator.py
│   ├── dynamic_query_service.py
│   ├── model_service.py
│   ├── chat_service.py
│   └── response_service.py
└── tests/
    ├── test_tenant_isolation.py
    ├── test_query_validation.py
    ├── test_dynamic_queries.py
    └── test_chat_pipeline.py
```

This is a proposed layout. Inspect the current repository before creating or moving files.

### Model service responsibilities

- Load the base model and adapter.
- Apply the correct chat template.
- Generate output within token and time limits.
- Parse the model response.
- Return a validated query-plan candidate.
- Handle inference failures and malformed outputs.

Load the model once per inference process. Avoid unintentionally loading duplicate model copies in every FastAPI worker.

For larger deployments, consider a separate model inference service.

### Chat service responsibilities

The chat service coordinates:

1. Authentication.
2. Tenant resolution.
3. Relevant operation context.
4. Model inference.
5. Query-plan validation.
6. Clarification handling.
7. Authorization.
8. Query execution.
9. Response generation.

The chat service must never bypass the tenant resolver or query validator.

### Example request

```json
{
  "message": "Show my attendance for this month"
}
```

### Example response

```json
{
  "answer": "You were present for 18 days this month.",
  "needs_clarification": false,
  "data": {
    "present_days": 18
  }
}
```

The count is illustrative. Production answers must be grounded in actual query results.

Use a stable Pydantic request/response contract and integrate with the existing authentication dependency.

---

## 13. Response Generation

The response service converts normalized query results into readable answers.

Example query result:

```json
{
  "present_days": 18
}
```

Possible answer:

```text
You were present for 18 days in October 2026.
```

The response generator must:

- Use actual query results.
- Avoid inventing missing values.
- Handle empty result sets.
- Respect the operation's data-access scope.
- Avoid exposing unnecessary sensitive fields.
- Distinguish between zero results and query failures.
- Return a clarification when required.

For sensitive numerical or date-based results, deterministic formatting is often preferable to unrestricted generative summarization.

---

## 14. React Frontend Integration

The React frontend should send messages to FastAPI and display structured responses.

Frontend responsibilities:

- Chat message input.
- Conversation rendering.
- Loading state.
- Clarification prompts.
- Empty-result handling.
- Error and retry handling.
- Optional attendance/timesheet tables.
- Authentication-session handling.

Do not implement database discovery, SQL generation, or tenant selection in the browser.

For every follow-up question, the backend must validate the current user and tenant again.

Conversation context may be used to resolve follow-up references, but previous messages must not be treated as proof of authorization.

---

## 15. New Tenant and New Table Behavior

### New tenant with the standard schema

1. Provision its schema from migrations.
2. Register the tenant.
3. Discover its metadata.
4. Reuse existing approved operations.
5. Allow authenticated employees to use the chatbot.

No model retraining is needed merely because a new organization or employee is added.

### New column or changed schema

1. Apply migrations.
2. Refresh the schema catalog.
3. Validate the affected operation mappings.
4. Update tests and permissions where necessary.

Schema discovery alone does not guarantee compatibility.

### New business capability

Suppose Tickora adds expense management.

1. Add and migrate the new tables.
2. Discover the new schema metadata.
3. Define approved operations.
4. Implement filters, joins, calculations, and authorization rules.
5. Add training and evaluation examples.
6. Evaluate whether the model needs further adaptation.
7. Test the feature against multiple tenants.
8. Enable the operation after approval.

Do not automatically authorize discovered tables or generate unrestricted SQL for them.

---

## 16. Security Requirements

Security is part of the core architecture, not a later enhancement.

Required controls:

- Trusted tenant resolution.
- Authentication on every chat request.
- Employee-level row scoping.
- Role-based permissions where required.
- Strict operation and field allowlists.
- Parameterized SQL.
- Safely quoted database identifiers.
- Read-only database access for read-only chatbot operations.
- Query timeouts and result limits.
- Rate limiting.
- Safe handling of model output.
- Protected secrets and database credentials.
- Minimal logging of sensitive information.
- Cross-tenant security tests.
- Auditable operation execution.

Do not permit the model to execute arbitrary SQL, choose a schema, change authentication context, or grant itself additional permissions.

State-changing actions such as clock-in/clock-out operations, leave approvals, and WFH approvals must use separately authorized business workflows. The initial chatbot should focus on approved read-only operations unless a write workflow is explicitly designed and tested.

---

## 17. Testing Strategy

Implement automated tests for the following areas.

### Tenant isolation

- An ABC employee cannot access XYZ data.
- Client-provided tenant identifiers cannot override authenticated context.
- Tenant caches do not leak metadata across organizations.
- Connection/session state cannot accidentally reuse another tenant's schema.

### Query validation

- Unknown operation IDs are rejected.
- Unknown fields and filters are rejected.
- Malformed JSON is handled safely.
- Unsupported date formats are rejected or normalized safely.
- Excessive date ranges and result sizes are limited.
- Unauthorized fields and operations are rejected.

### Correctness

- Date ranges respect the organization's timezone.
- Month boundaries are correct.
- Attendance calculations follow approved business rules.
- Empty result sets produce accurate responses.
- Aggregations match direct SQL test results.

### Model behavior

- Unseen questions map to the correct operation.
- Paraphrases produce equivalent plans.
- Ambiguous questions trigger clarification.
- Unsupported requests are handled correctly.
- Malformed or malicious outputs cannot bypass validation.

### Integration

- Authentication works with the existing application.
- The tenant resolver selects the correct tenant.
- Query execution returns the expected records.
- The frontend displays successful results and errors correctly.
- Model and database failures are handled without leaking internal details.

---

## 18. Deployment and Monitoring

Before production:

1. Deploy to a staging environment.
2. Apply tenant migrations.
3. Verify tenant provisioning and resolution.
4. Deploy the evaluated model artifact.
5. Run end-to-end tests with at least two independent test tenants.
6. Perform security and concurrency tests.
7. Measure model inference and query latency.
8. Release to a limited pilot group.
9. Monitor operation failures and answer correctness.
10. Expand deployment after validation.

Monitor:

- Model inference latency.
- Invalid query-plan frequency.
- Operation selection accuracy.
- Database query latency and failures.
- Authorization failures.
- Tenant provisioning and migration failures.
- Query timeouts.
- Model and adapter version.
- Operation registry version.

Use request IDs and safe operational metadata for debugging. Do not log raw attendance, leave, or other sensitive data unnecessarily.

Maintain versioned model artifacts and a rollback mechanism.

---

## 19. Recommended Implementation Order

Complete the work incrementally in this order.

### Phase 1 — Repository and schema audit

Inspect the current codebase, migrations, authentication, database configuration, and endpoints.

Resolve differences between the prototype and the actual tenant schema.

### Phase 2 — Tenant resolution

Ensure every request obtains the correct tenant from trusted authentication context.

### Phase 3 — Schema catalog

Discover tables, columns, keys, and relationships for each tenant.

### Phase 4 — Operation registry

Define approved operations using the real database schema and business rules.

### Phase 5 — Query engine

Implement strict validation, authorization, parameterized SQL, and normalized results.

### Phase 6 — Dataset preparation

Create and validate examples that match the final query-plan contract.

### Phase 7 — Fine-tuning

Train and evaluate the model in Google Colab.

### Phase 8 — FastAPI integration

Connect model inference to the validated query execution pipeline.

### Phase 9 — React integration

Implement the chat interface and response handling.

### Phase 10 — Security and deployment

Validate tenant isolation, correctness, performance, monitoring, and recovery.

Do not implement all phases simultaneously. Complete one vertical slice first.

---

## 20. End-to-End Example

Assume:

- ABC Technologies has organization ID `101`.
- Its schema is `tenant_abc`.
- The authenticated employee has internal user ID `501`.
- The employee asks: "How many days was I present this month?"
- The current reporting month is October 2026.

### Step 1: Authenticate

FastAPI validates the session or JWT and resolves the authenticated employee.

### Step 2: Resolve tenant

The trusted organization mapping selects `tenant_abc`.

### Step 3: Generate query plan

The model returns:

```json
{
  "operation": "attendance.count",
  "filters": {
    "period": "this_month",
    "status": "present"
  },
  "fields": [],
  "needs_clarification": false
}
```

### Step 4: Validate

The backend checks that `attendance.count` is approved and that the filters are valid.

### Step 5: Resolve dates

The backend converts the relative period into explicit dates using the configured reporting timezone.

### Step 6: Execute

The query engine uses the trusted schema, authenticated user ID, approved operation, and parameterized date/status values.

### Step 7: Generate answer

If the verified result is 18, the response service returns:

```json
{
  "answer": "You were present for 18 days in October 2026.",
  "needs_clarification": false,
  "data": {
    "present_days": 18
  }
}
```

### Step 8: Repeat for another tenant

When XYZ asks the same question, the shared model can generate the same logical operation. The backend resolves XYZ's tenant and authenticated employee independently, then executes against XYZ's authorized data.

No retraining is required merely because XYZ signs up.

---

## 21. Instructions for Antigravity AI

When working in this repository, follow these rules.

1. Read this README before modifying the code.
2. Inspect the actual repository structure and current implementations.
3. Inspect the real SQL migrations before assuming any table, column, key, or relationship exists.
4. Identify which components already exist and reuse them where appropriate.
5. Do not assume that illustrative code in this document is already implemented.
6. Do not replace working authentication, database, or API components without justification.
7. Preserve compatibility with the existing FastAPI backend and React frontend.
8. Resolve the prototype/tenant-schema mismatch before implementing production queries.
9. Implement tenant resolution and security before dynamic query execution.
10. Keep model output separate from authorization decisions.
11. Use strict structured output and validate every model-generated query plan.
12. Never execute unrestricted model-generated SQL.
13. Never authorize a database table solely because schema discovery found it.
14. Keep training data free of real tenant secrets and sensitive employee records.
15. Keep the training output schema consistent with the production query-plan schema.
16. Add tests for every new operation and security-sensitive component.
17. Run relevant tests after each implementation phase.
18. Do not claim that a phase is complete unless its code and tests support that claim.
19. Document any schema assumptions, unresolved decisions, and implementation limitations.
20. Implement one end-to-end read-only attendance query before expanding to other capabilities.

### Expected workflow

Before editing:

- Inspect the repository.
- Identify existing modules and tests.
- Compare the actual schema against this document.
- Produce a concise implementation plan listing files to modify and create.

Then implement incrementally:

- Make one coherent change at a time.
- Run the relevant tests.
- Fix regressions before proceeding.
- Update this README when the implemented architecture changes.

Do not rewrite the entire application in one operation.

---

## 22. Definition of Done

The initial implementation is complete only when:

- [ ] The actual tenant schema is verified and mapped.
- [ ] Tenant provisioning and resolution work.
- [ ] Cross-tenant access is blocked and tested.
- [ ] The schema catalog discovers metadata per tenant.
- [ ] The operation registry exposes only approved operations.
- [ ] Query-plan validation rejects malformed and unauthorized requests.
- [ ] The query engine executes parameterized queries safely.
- [ ] The training dataset matches the production query-plan schema.
- [ ] The fine-tuned model passes held-out evaluation.
- [ ] FastAPI integrates model inference and database retrieval.
- [ ] React displays accurate answers and clarification prompts.
- [ ] Tests cover security, correctness, and error handling.
- [ ] Deployment and monitoring procedures are documented.

## Final Design Principle

Tickora AI should be built as a **shared fine-tuned language model with tenant-aware schema discovery, an explicitly approved operation registry, and a secure PostgreSQL execution layer**.

The model understands the employee's intent. The schema catalog describes the available database structure. The operation registry defines supported capabilities. The backend enforces authorization and executes queries. The response service presents the actual results.

This architecture allows new organizations to use the existing chatbot without retraining for each signup, while keeping tenant isolation, database correctness, and security under backend control.
