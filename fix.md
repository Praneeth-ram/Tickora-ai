Prompt: fix LLM answer defects in attendance responses

We have an LLM answer step for Tickora. The database returns results, compute_facts builds a JSON facts object, write_answer asks the LLM to phrase an answer, and passes_answer_check decides whether to keep the LLM reply or fall back to the template. The design must not change: tables stay as they are, the LLM only phrases facts, RBAC is unchanged, and the template is the fallback.

The following defects were observed in flag-on output. Fix all of them.

Defects to fix

Negated facts accepted. Replies such as "no late days" or "no absent days" pass when the facts show a positive count for that status. The check compares numbers only, so a negation is not caught.
Minute totals leak through. Replies such as "166 hours and 28 minutes (9,988 minutes)" pass because 9988 is present in the facts. Minute totals must never appear in a reply when hours and minutes are given.
Unit errors pass. Some replies state time in days. The unit check must reject any reply that uses "day" for hours or minutes.
Misplaced punctuation. "October, 2026" appears when the period text has a comma in the wrong place. The rules must forbid this.
Repetition across sentences. Some replies restate the same figures in two sentences.
Awkward status labels. Replies quote status labels in quotation marks, for example "'late' status". Use plain words.
Non-idiomatic absence wording. "0 days of absence" should read as "no absences".

Files and changes

A. backend/services/answer_writer.py

In ANSWER_RULES, append these rules after the existing rule 10:
11. Never write "no" or "none" about a status whose count is above zero.
Never write minute totals in brackets or otherwise. When hours and minutes are given, use only hours and minutes.
Use "hours" and "minutes" for time totals. Never use "days" for time.
Use singular and plural correctly: "1 hour", "2 hours", "1 day", "2 days".
Do not repeat the same figures in more than one sentence.
Write status words plainly, without quotation marks.
Express zero absences as "no absences", not "0 days of absence".
In passes_answer_check, add these checks, keeping the existing ones:
Reject the reply if it contains a negation word ("no", "none", "zero") directly before a status label whose count in the facts is above zero. Use the group labels in facts["groups"], and the status and count keys for single counts.
Reject the reply if it contains a parenthesised minutes figure, for example a pattern matching (\d[\d,]*\s*minutes).
Reject the reply if the measure is "worked time" or "overtime" and the reply contains the word "day".
Reject the reply if the reply contains a comma between a month name and a year, for example "October, 2026".
Keep the existing checks: minimum word count, the no-records check when found is true, and every number in the reply must appear in the facts.

B. backend/services/payload/answer_payload.py

In compute_facts, remove total_minutes from the worked-time and overtime facts. Keep hours and minutes.
Keep period_text as it is, but strip surrounding whitespace.
For status values, keep the existing labels. Do not add quotation marks.

C. Tests

Create backend/services/test_answer_check.py with cases for each defect:

"You had 2 late days." passes when the facts show late count 2.
"You had no late days." fails when the facts show late count 2.
"166 hours and 28 minutes (9,988 minutes)." fails.
"166 days and 28 hours." fails.
"14 present days in October, 2026." fails.
A correct reply with the right unit and no negation passes.

Run uv run pytest backend/services/test_answer_check.py -q. All tests must pass before running the flag-on eval.

Constraints

Do not change the table route, RBAC, or the planner.
Do not remove the template fallback.
Do not add new model calls.
Keep the change to the three files above, plus the new test file.