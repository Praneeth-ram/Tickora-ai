# Parity Log: Policy On vs Baseline

Date: 6 November 2026
Baseline: route_check_before.csv (EMP001, 3 November 2026), compound_false_1.csv
Runs compared: parity_emp001_single.csv, parity_emp002_single.csv, parity_emp001_compound.csv, parity_emp002_compound.csv
Flag: AGENT_ORCHESTRATION=true

## Status key

- Resolved, re-tested: defect fixed and verified in the frontend.
- Accepted: expected difference, with reason and evidence.
- Open: difference that still needs a task.

## Differences

| # | Question | Role(s) | Baseline | New | Reason | Status |
|---|---|---|---|---|---|---|
| 1 | Is October 31 a holiday? | EMP001, EMP002, EMP011 | There are no holidays on 31 October 2026. | Same | DEFECT-1 (name check) fixed in subject_resolution.py | Resolved, re-tested |
| 2 | Is October 31 a holiday and what was my clock-in time on October 5? | EMP001, EMP002, EMP011 | Holiday answer + clock-in 9:39 AM | Holiday answer + clock-in for EMP001 and EMP002; EMP011 gets "couldn't find an attendance record" | DEFECT-1 fixed; EMP011 has no record for 5 Oct 2026 (data, not a code change) | Resolved, re-tested |
| 3 | How many pending tasks do I have? | EMP001 | There are 3 pending tasks. | No pending tasks were found. | Task scope changed to assignee only. SQL: assigned_pending = 0, managed_pending = 3 | Accepted (T2) |
| 4 | What was my clock-in time yesterday? | EMP001 | 2 November 2026 | 4 November 2026 | Date-dependent: the baseline was recorded on 3 November | Accepted |
| 5 | Personal answers (clock-out, leave balance, leave status, WFH status, gross, deductions, net, loans, WFH count, leave types) | EMP001 vs EMP002 | EMP001 data | EMP002's own data | Each role sees only its own records | Accepted |
| 6 | Loan answers (remaining emergency loan, total emergency loan, active loans) | EMP001 vs EMP002 | EMP001 data | EMP002 has no loans | Personal data per role | Accepted |
| 7 | What is my remaining emergency loan amount and is October 2 a holiday? | EMP001, EMP002 | Error: "Date range start must not be after end." | Loan answer and holiday answer | Loan/date fix from earlier | Accepted |
| 8 | Show my leave history and my WFH requests | EMP001 | Leave and WFH sections | WFH sentence only | Table sections are blank in combined answers (DEFECT-4) | Open (T7) |
| 9 | Clock in and clock out on October 5 and is October 31 a holiday? | EMP001, EMP002 | Attendance part says "No records for November 2026" | Same | Compound date resolution uses the current month (DEFECT-2) | Open (T5) |

## Open items

- T5: fix DEFECT-2 (row 9).
- T7: decide presentation for combined answers with tables (row 8).
- T4: answer-quality fixes (penalty deduction, active loans, status naming, zero-minutes wording, date-less periods).

## Sign-off

- DEFECT-1: closed (rows 1 and 2), verified for EMP001, EMP002, EMP011.
- T1 and T2: complete.