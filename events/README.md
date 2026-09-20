# Learning Events

This directory is an append-only record of durable learning evidence. Do not paste full chat transcripts here.

One JSON object per line is the implemented format. The default ledger is `learning_events.jsonl`; it is created by `python -m scripts.append_event` after a valid real event is supplied. This illustrative event follows the current 1.0 contract; it is not real learner evidence:

```json
{
  "schema_version": "1.0",
  "event_id": "demo-20270101-english-001",
  "timestamp": "2027-01-01T09:00:00Z",
  "event_type": "attempt",
  "subject": "english",
  "unit_ids": ["eng.reading.distractor.scope"],
  "activity": "review",
  "source_ref": "demo-only",
  "attempt": {
    "question_id": "demo-reading-001",
    "result": "partial",
    "answer_mode": "independent",
    "process_check": "suspicious",
    "assistance_level": 0,
    "time_minutes": 25,
    "confidence_before": 0.6,
    "evidence": "Identified the passage evidence but accepted an option with an enlarged scope."
  },
  "next_action": "Generate two contrastive options and retest tomorrow"
}
```

Historical events should not be rewritten merely because the current estimate changes. Derived state belongs under `state/`.

Diagnosis changes are also append-only. A repeated `diagnosis_id` must point to the latest prior revision through `supersedes_event_id`. Only the current `confirmed` revision contributes to durable error-pattern counts.

Confirmed error tags belong to a separate diagnosis event, not top-level attempt fields. See `../docs/DATA_CONTRACTS.md`. Keep demonstrations in an isolated ledger, never in the real history.

Mobile requests are pending evidence until the Core checks and appends them. Stable request and event IDs prevent re-importing the same attempt; follow `../docs/MOBILE_DESKTOP_WORKFLOW.md` and return an archive receipt.
