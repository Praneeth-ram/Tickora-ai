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

### 3.2 Facts (attendance)
- `compute_facts` in `backend/services/payload/answer_payload.py`:
  - count facts include `count`, `status`, `period_text`, `found`;
  - minute totals are split into `hours` and `minutes` (no raw minute total);
  - group-by facts include labelled `groups`;
  - `period_text` comes from `period_phrase`.
- Multi-aspect single-day questions (clock in, clock out, work location) are answered together. `requested_aspects` and `fields_for_aspects` select only the requested fields, and the template builds one sentence covering all aspects.

### 3.3 Answer step
- `write_answer` in `backend/services/answer_writer.py`: sends the rules and facts to the base model with a 150-token cap.
- `ANSWER_RULES`: one or two sentences, use only facts, use `period_text` exactly, say "you", no "instances" or "times", no quoted status labels, no comma between month and year, no "this"/"last"/"next" before a month, no "the specified period".
- `passes_answer_check` rejects: short replies; numbers not in facts; "no" next to a status with positive count; minutes in brackets; "day" for time totals; comma between month and year; repeated month; "no records" when data exists; bare numbers in breakdowns; quoted status labels; "instances"/"times".

### 3.4 Template fixes (attendance)
- Per-status questions route to the breakdown.
- Overtime and worked-time sentences use singular/plural correctly and show the month once.
- Partial-month wording uses "so far".
- Leave per-status question returns a clear message, not a plain count.

### 3.5 Tests
- `backend/services/test_answer_rules.py`: comma rule, singular count, relative period rule, vague period rule, per-status routing (5 tests, passing).
- Attendance eval: `scripts/eval_narration.py` (21 questions), run flag-off and flag-on.

### 3.6 Verified results
- Flag-off: all attendance figures match the expected values.
- Flag-on: wrong replies are rejected and the template is shown. Remaining known issue: "half day days" passed one check (fix pending, see §5).
- Two-question single-day case (clock in and work location) returns both aspects.

## 4. What is not implemented

- LLM answers for leave, WFH, timesheet, holiday, leave balance, task, loan, and payroll. These still use f-string templates.
- Generic facts handlers per result shape (count, sum, group-by, rows, single record).
- Per-entity field maps (allowed fields, labels, units).
- Per-entity eval sets.
- Entity-specific rules for money (loan, payroll).

## 5. Pending work

### 5.1 Fix before flag-on rollout
1. "half day days" passes the check: add a check for a unit word repeated after "day" or "half day".
2. Zero-count wording: choose "No absences in October 2026." or "No absent days were found…" and make the template and the rule match.
3. Confirm the template for half days reads "No half day attendance records were found…" (not "half day days").

### 5.2 Refactor attendance into the shared handlers
1. Move the shape code in `compute_facts` into named handlers: `_count_facts`, `_minutes_facts`, `_groups_facts`, `_rows_facts`, `_single_record_facts`.
2. Move the attendance field map into a shared field-map module.
3. Rerun the attendance eval; output must match before the refactor.

### 5.3 Generic pipeline for other entities (Option A)
1. Leave requests (count, list, status): handler, field map, rules check, eval set.
2. WFH requests: same as leave.
3. Timesheets (latest status, list): handler and eval.
4. Holidays (count, list): handler and eval.
5. Leave balance (per type: allocated, used, pending): handler and eval.
6. Tasks (count, sum, group by status): handler and eval.
7. Payroll and loan: handler, strict amount check (every amount and currency must match facts exactly, no rounding), and eval. Enable last.

Each entity is enabled only after its flag-on eval has no wrong replies.

### 5.4 Operations
- Rotate database passwords and `JWT_SECRET_KEY` (credentials were shared in conversation).
- Keep `LLM_NARRATION_ENABLED=False` in production until the rollout decision.
- Remove dead narration code (`_maybe_narrate`, `_payload_for`, `_entity_specs`, `NARRATABLE_INTENTS`) and unused imports.

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