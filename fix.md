# Tickora LLM Answer Generation: Implementation Plan and Status

## 1. Purpose

Tickora answers HR questions from database results. Simple detail answers are phrased by the LLM from facts that the backend computes. Large record lists are shown as tables. Every figure comes from the database; the LLM only writes the sentence.

## 2. Design (agreed, do not change)

```
User question
  → access gate (RBAC, unchanged)
  → planner (LLM, LoRA on; returns a query plan)
  → correction (code: dates, status, identity, fields)
  → execute (SQLAlchemy, scoped, parameterised)
  → result shape
      ├─ table route (no LLM): show_table and more than 5 rows
      └─ detail route (LLM):   counts, specific details, breakdowns
                              with 4 or fewer groups, lists of 5 rows or fewer
  → facts handler (code builds labelled JSON for this shape)
  → write_answer (base model, LoRA off, rules applied)
  → passes_answer_check (number, unit, wording rules)
      ├─ pass → LLM reply
      └─ fail or error → template text (fallback)
  → response (table, intent, period unchanged)
```

Constraints:
- No change to the planner, RBAC, or the table route.
- The template is always the fallback.
- The LLM never computes totals, rounds money, or chooses figures.

## 3. What is implemented

### 3.1 Routing and wiring
- `choose_route` in `backend/services/answer_router.py`: table or LLM.
- `_route_answer` in `backend/agents/nodes.py`: called from `execution_node` for every entity. Returns the template when the flag is off, when the route is table, or when the question is a "per status" question with no groups.
- Flag `LLM_NARRATION_ENABLED` in `config.py` (default `False`) and `.env`.

### 3.2 Facts
- `compute_facts` in `backend/services/payload/answer_payload.py` dispatches to named count, sum, group-by, row, and single-record handlers.
- Entity field labels and singular/plural units come from `backend/services/payload/entities.py`; sensitive fields and role-hidden task scores do not reach the model.
- Minute totals are split into `hours` and `minutes`; unsupported result shapes fall back to the template.
- Payroll amount questions use a separate minimal-facts path with exact amount/currency validation; payroll tables and loans remain on templates.
- Multi-aspect single-day questions (clock in, clock out, work location) are answered together. `requested_aspects` and `fields_for_aspects` select only the requested fields, and the template builds one sentence covering all aspects.

### 3.3 Answer step
- `write_answer` in `backend/services/answer_writer.py`: sends the rules and facts to the base model with a 150-token cap.
- `ANSWER_RULES`: one or two sentences, use only facts and the entity's own unit, use `period_text` exactly, say "you", no "instances" or "times", no quoted status labels, no comma between month and year, no "this"/"last"/"next" before a month, no "the specified period".
- `passes_answer_check` rejects: short replies; numbers not in facts; "no" next to a status with positive count; minutes in brackets; "day" for time totals; comma between month and year; repeated month; "no records" when data exists; bare numbers in breakdowns; quoted status labels; "instances"/"times".

### 3.4 Template fixes (attendance)
- Per-status questions route to the breakdown.
- Overtime and worked-time sentences use singular/plural correctly and show the month once.
- Partial-month wording uses "so far".
- Leave per-status question returns a clear message, not a plain count.

### 3.5 Tests and eval sets
- `backend/services/payload/test_answer_payload.py` covers entity counts, sums, groups, rows, single records, and sensitive-entity fallback.
- `backend/services/test_answer_rules.py` and `backend/services/test_response_generation.py` cover answer validation and attendance wording.
- `backend/services/test_payroll_narration.py` covers payroll metric routing, personal scope, exact amounts/currencies, and total-period coverage.
- `tests/fixtures/narration_entity_questions.json` supplies leave, WFH, timesheet, holiday, leave-balance, and task questions to `scripts/eval_narration.py`.
- Live flag-off/flag-on evaluations are still required before enabling narration for an entity.

### 3.6 Verified results
- Focused unit tests for the shared facts and answer rules pass.
- The live database narration evaluation and test-environment UI check have not been run as part of this implementation.
- Keep `LLM_NARRATION_ENABLED=False` until the flag-off/flag-on evals pass.

## 4. What is not implemented

- Exact money/currency validation and narration for loans; they remain on templates and are intentionally excluded from narration.
- Live per-entity flag-on/flag-off evaluation and test-environment UI checks.
- Operational credential rotation, which must be performed by an authorized operator outside this code change.

## 5. Pending work

### 5.1 Fix before flag-on rollout
- Repeated-unit rejection, zero-count wording, and half-day template wording are implemented and covered by focused tests.

### 5.2 Refactor attendance into the shared handlers
- Named shape handlers and the shared entity field map are implemented.
- Rerun the attendance eval and compare flag-off answers before rollout.

### 5.3 Generic pipeline for other entities (Option A)
- Leave requests, WFH requests, timesheets, holidays, leave balances, and tasks use the shared facts pipeline and have per-entity question sets.
- Explicit personal gross, net, and deduction amount questions use a payroll-only facts path; broad payroll/table requests stay on the existing table/template route. Totals require coverage for every requested month, and accepted replies must preserve every requested metric, amount, and currency exactly.
- Run each entity's flag-on evaluation and keep the template as fallback for rejected replies.
- Loans remain excluded until strict amount/currency checks and evaluations are implemented. Payroll narration still requires live flag-on evaluation before production enablement.

Each entity is enabled only after its flag-on eval has no wrong replies.

### 5.4 Operations
- Rotate database passwords and `JWT_SECRET_KEY` through the approved secrets-management process; do not put credentials in source.
- Keep `LLM_NARRATION_ENABLED=False` in production until the rollout decision.
- The unused `_maybe_narrate`, `_payload_for`, `NARRATABLE_INTENTS`, and related imports have been removed. `_entity_specs` remains because the active facts path uses it.

## 6. Rollout

1. Attendance: fix §5.1, refactor §5.2, run eval, test-environment UI check.
2. Each entity in §5.3 order, each with its own eval and test-environment check.
3. Production: enable per entity, only after its checks pass.

## 7. Checks before enabling any flag

- Flag-off eval matches expected figures.
- Flag-on eval has no wrong replies (no unit, figure, period, comma, or negation errors).
- Table questions are identical with the flag on and off.
- Unit tests pass.
- Log shows `facts:` for LLM answers and `answer rejected` for fallbacks.