### Model: holiday count returns an unsupported filter

- Question: "How many holidays are there in 2026?"
- Model output: `holiday.count` with a `year` filter. The filter is not in the allowed list, so the plan is rejected.
- Effect on users: none. The keyword planner selects `holiday.count`, and the correction step sets the 2026 date range from the question. The answer is correct.
- Status: accepted. Retrain or constrain decoding in a later release to remove the rejection.