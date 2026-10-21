# Tickora AI — AI Model

Tickora AI uses a custom intent-classification model to route employee questions to data-backed workflows. Employee-specific answers should be grounded in PostgreSQL records, not guessed by the model.

## Current design
- Custom Transformer-based intent classifier implemented with PyTorch
- Project tokenizer and vocabulary
- Seven intent categories
- Chat service that receives the question and authenticated employee ID
- Repository workflows that retrieve relevant records
- Structured chat response that may include an answer, intent, data, and display metadata

This is a custom model project; it is not described as a fine-tuned pretrained language model.

## Intent categories
1. `attendance_records`
2. `attendance_summary`
3. `holiday_lookup`
4. `leave_status`
5. `schedule_lookup`
6. `timesheet_lookup`
7. `wfh_status`

## High-level flow

```text
Employee question
       |
       v
FastAPI chat endpoint
       |
       v
JWT-authenticated employee identity
       |
       v
Chat service -> tokenizer -> Transformer intent classifier
       |
       v
Intent-specific repository/database workflow
       |
       v
Structured result and response
       |
       v
React chat interface
```

Confirm exact runtime behavior in `backend/services/chat_service.py` and `ai_model/`.

## Recorded development details
- Dataset: `data/intent_dataset_merged.jsonl`
- 569 unique examples were reported in a merged dataset
- Seven intent classes
- Vocabulary size around 100 was reported in an earlier run
- A previous model had 418,695 parameters
- A checkpoint was recorded at `data/artifacts/tickora_intent_model.pt`

These are historical development snapshots. Re-run the current scripts before publishing them as current metrics.

## Training
The recorded training entry point is:

```powershell
uv run python ai_model/train.py
```

Check the current script for required arguments and paths before running. The earlier local environment used CPU execution with CUDA unavailable.

The project has been experimenting with grouped train/validation/test splits to reduce leakage between similar paraphrases. Do not rely on earlier random-split accuracy as a generalization estimate without reviewing the split strategy and evaluation results.

## Evaluation recommendations
- Keep paraphrases of the same underlying question in the same split.
- Check for near-duplicate leakage across splits.
- Verify class balance in train, validation, and test sets.
- Report per-class precision, recall, F1, and overall accuracy.
- Inspect confusion matrices and low-confidence predictions.
- Test typos, ambiguous wording, out-of-scope questions, and unknown tokens.
- Verify that the predicted intent triggers the correct database workflow.
- Ensure database queries always use the authenticated employee identity.

## Limitations
- Classification quality depends on the size and coverage of labeled examples.
- Unseen wording and ambiguous requests may cause intent errors.
- The current design covers the seven categories listed above.
- Re-evaluate after changes to the dataset, split strategy, tokenizer, or model.
