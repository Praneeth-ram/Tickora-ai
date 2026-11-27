You are a senior Python engineer and LLM-application security reviewer. Review ONLY the
response-generation layer of Tickora, an HR chatbot (FastAPI, LangGraph, PostgreSQL, a local
Qwen model with a LoRA adapter). Do not review planning, authentication, or SQL generation
except where they directly affect the text or table a user sees.

Do not modify code. Report findings. Quote the exact code (file, function, line) for every
finding. If you cannot see a file, say so instead of assuming what it contains.

# SCOPE (review these, plus anything they call)
- backend/services/answer_writer.py       (prompt rules, write_answer, answer_check_failure,
                                           compound_answer_check_failure)
- backend/services/fact_verifier.py       (verify_against_facts)
- backend/services/payload/answer_payload.py, builders.py, shape.py, entities.py
                                          (compute_facts, merge_compound_facts, specs)
- backend/services/answer_builder.py, payroll_narration.py, request_answer_builder.py
- backend/services/answer_router.py       (choose_route)
- backend/agents/nodes.py                 (_route_answer, narration blocks, compound_node,
                                           execution_node, clarify_node, error_node)
- backend/services/llm_chat_service.py    (execute_and_format and every _answer_* function,
                                           _text_result, _third_person, template answers)
- backend/services/model_inference.py     (generate_text only)
- backend/main.py                         (_localize, answer cache use, result shaping)

# HOW TO REVIEW
1. Trace one request end to end for each entity: attendance, leave_request, leave_balance,
   wfh_request, timesheet, holiday, task, payroll_summary, loan_request. Write the call path
   from the query result to the final JSON the client receives.
2. For each hop, ask: where can a wrong, ungrounded, unauthorized or confusing sentence appear?
3. Prefer evidence over opinion. If something is a risk but you cannot prove a failing input,
   label it "risk", and give the input that would trigger it.

# REVIEW CHECKLIST

A. CORRECTNESS OF FACTS
 - Is every number computed in code (counts, sums, minutes to hours, differences), never left
   for the LLM to calculate? Find any place the LLM does arithmetic or rounding.
 - Decimal vs float for money. Rounding mode. Currency formatting and thousands separators.
 - Units: minutes vs hours, days vs requests, gross vs net vs deductions.
 - Off-by-one in date ranges (inclusive end dates), timezone and "today" handling.
 - Does the sentence's count always equal the rows in the table? Find any path where a
   truncated list (limits, pagination) is described as the full total.
 - Aggregates over many rows: is the period and the filter actually applied to the query that
   produced the number, or only shown in the label? (Known past bug: a reused period changed
   only the label, so "deductions that month" listed every month.)

B. GROUNDING AND THE VERIFIER
 - What does answer_check_failure / verify_against_facts actually check? List what it does
   NOT check (names, statuses, dates, units, plural forms, extra sentences, negations,
   comparatives like "more than", causes, advice).
 - Can a response pass verification while being wrong? Give a concrete example.
 - Is the deterministic template answer always available when narration is rejected, times out,
   is disabled, or raises? Find any path that returns an empty, partial or raw-LLM string.
 - Are there paths that skip verification (compound answers, direct answers, cached answers,
   clarifications)?

C. PROMPT AND LLM USE
 - Review BASE_RULES and ENTITY_RULES for contradictions, rules the code cannot enforce, and
   rules that conflict across entities (e.g. "start with Your" vs a leading period phrase).
 - Is user-authored text (leave reasons, task titles/descriptions, adjustment reasons, names)
   placed into the FACTS JSON? This is INDIRECT PROMPT INJECTION. Check whether it is
   truncated, escaped, labelled as data, or excluded for narration.
 - Is the question itself placed in the prompt? Can it override the rules?
 - Generation settings: max_new_tokens truncation (cut-off sentences), temperature/determinism,
   stop conditions, the time limit, behavior on empty output.
 - Concurrency: generate_text uses a shared model and a one-slot semaphore. What does the user
   see when it is busy? Is narration optional so a busy model never blocks a correct table?

D. AUTHORIZATION AND PRIVACY IN OUTPUT
 - Can any response include another employee's data, team or organization totals, payroll,
   or identifiers for a user who is not entitled to them?
 - "my"/"I" questions from admin roles: is the subject carried into the facts, so the sentence
   cannot describe a team total as the user's own figure?
 - _localize and _third_person: regex rewriting of text. Can it corrupt a sentence, miss a
   pronoun, or alter a name that appears inside quoted data?
 - Are internal details ever exposed: table or column names, SQL, stack traces, internal IDs,
   operation ids, request ids in text?
 - Do logs (narration_debug_logging or similar) write answers, facts or names? Check against
   the claim that sensitive data is not logged.
 - Cache: is the answer cache key bound to employee, role, subject, today's date and context?
   Can a cached answer be served to the wrong user or after the data changed? Does a cache hit
   save the same follow-up context as a miss?

E. LANGUAGE AND FORMAT
 - Singular and plural ("1 record"), is/are, was/were, a/an.
 - Capitalization after a leading phrase ("In September 2026, Your ...").
 - One date format everywhere; month-year comma rules; period wording ("for", "in", "from ... to").
 - Empty result wording: names the period and the unit, never "No records were found" when the
   facts show records.
 - Contradictions between the text and the table in the same response.
 - Wording a user could misread: a count with no period, a count with no status, "attendance"
   when "absent days" was asked.

F. ROUTING (text vs table vs both)
 - choose_route and show_table: which questions get a table, a sentence, or both? Find
   questions where the user gets only an unhelpful half (a big table and no answer, or a
   sentence that hides rows they asked to see).
 - Compound questions: ordering, part-to-entity mapping, period handling, partial failure
   (one part fails, the others succeed).

G. ERROR, EDGE AND FALLBACK BEHAVIOR
 - Empty results, a single row, thousands of rows, null fields, missing joins, unusual enum
   values, inactive employees, zero and negative numbers, very long text, non-ASCII names.
 - Invalid dates, future periods, ranges longer than the limit.
 - Exceptions inside narration, builders or verification: caught, logged without data, and
   replaced by the template answer? Or can they surface as a 500?

H. MAINTAINABILITY AND TESTABILITY
 - Duplicate or dead code, near-identical _answer_* functions, 1,000+ line functions, regex
   piles that can conflict, magic strings, hidden global state (ContextVars: actor, subject).
 - Is every sentence template covered by a test? List entities, operations and edge cases with
   no test. Identify tests that only assert "no exception".
 - Can the response builders run without the database and the model (pure functions)?

# KNOWN ISSUES TO CONFIRM OR REFUTE (verify each, do not assume)
 1. A reused follow-up period is shown but not applied to the query filters.
 2. normalize_and_correct_plan drops any status filter the question text does not name, so a
    carried status is lost on "What about September?".
 3. A follow-up for an admin lost "my", producing a team-wide count worded as "Your attendance".
 4. "Your" is capitalized mid-sentence when the LLM puts a period phrase first.
 5. A cache hit saves only the operation id, not period, filters or subject.
 6. The verifier accepts answers whose numbers appear in FACTS but that describe the wrong thing.

# OUTPUT FORMAT
Return:
1. A one-paragraph overall assessment and the three highest-risk areas.
2. A findings table, sorted by severity:
   | ID | Severity | Category (A-H) | File:function:line | What is wrong | Evidence (code or failing input) | Recommended fix | Test to add |
   Severity: CRITICAL (wrong data, data leak, injection), HIGH (misleading or wrong answer
   in common cases), MEDIUM (edge cases, fragile logic), LOW (style, naming, duplication).
3. For each known issue above: CONFIRMED / REFUTED / CANNOT VERIFY, with evidence.
4. A list of missing tests, grouped by entity and operation.
5. A short "do first" list: the 5 changes with the best risk reduction per hour of work.
Do not pad the report. If a category has no findings, write "No findings" and list what you checked.