Task: Fix the shadow-mode verifier comparison in scripts/eval_narration.py.

Context:
- The project is Tickora (FastAPI + LangGraph + LoRA model). We are in shadow mode:
  the old checker (answer_check_failure in backend/services/answer_writer.py) still
  decides what the user sees. The new checker (verify_against_facts in
  backend/services/fact_verifier.py) only logs its verdict.
- backend/agents/nodes.py, in _route_answer's attendance path, logs a line:
  "verifier compare: old=<old_reason> new=<new_reason> answer=<answer>"
- The eval script must show that line for every attendance answer, including
  answers the LLM accepted (route=llm). Right now the line appears only in the
  TRACE of rejected rows, because TRACE is None for route=llm.
- Do not change nodes.py, answer_writer.py, fact_verifier.py, or any user-facing
  behaviour. This task changes only the eval script.

Problems in the current scripts/eval_narration.py:
1. Inside the question loop there is a block that loops over rows and reads
   r.get("_messages"). That key does not exist, the block runs once per question,
   and it must be deleted.
2. The rows.append dict does not include a "verifier" key, so no VERIFY line prints.

Required changes:
A. Delete the block that starts with "for r in rows:" inside the question loop,
   the one that sets r["verifier"] from r.get("_messages").
B. In the rows.append dict, add this key directly after "trace":
       "verifier": next((m for m in capture.messages if m.startswith("verifier compare")), None),
C. In the final print loop, directly after the REJECTED print, add:
       if r.get("verifier"):
           print("VERIFY:", r["verifier"])
D. After the existing SUMMARY block, add a comparison summary. Parse each row's
   "verifier" string into old and new reasons (the text between "old=" and " new=",
   and between " new=" and " answer="). Count rows in four groups:
     pass/pass   old is None and new is None
     pass/fail   old is None and new is not None
     fail/pass   old is not None and new is None
     fail/fail   old is not None and new is not None
   Print the four counts, then write every row that has a verifier line to
   tests/fixtures/verifier_compare.txt, one line per row:
       <group> | <entity> | Q: <question> | A: <answer>
   Rows without a verifier line are skipped. Do not print the answers
   a second time in the terminal.
E. Keep the existing behaviour for every other field and print statement.

Acceptance criteria:
- Running the eval with LLM_NARRATION_ENABLED=True prints a VERIFY: line for
  every attendance row, including route=llm rows.
- The SUMMARY prints the four comparison counts.
- tests/fixtures/verifier_compare.txt exists and has one line per attendance row.
- The script still runs with the flag off (it should abort as before).
- No other file is changed.

Report back: the diff for scripts/eval_narration.py, the four comparison counts,
and the number of VERIFY lines.