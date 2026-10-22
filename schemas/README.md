# Data Contracts

Version 1.0 contracts are implemented for knowledge units, diagnoses, learning events, derived state, and scheduling requests. The JSON Schema files are documentation and interoperability contracts; `scripts/contracts.py` provides dependency-free runtime validation.

The contracts must support:

- subject-specific evidence;
- personal explanations and mnemonics;
- prerequisites and transfer links;
- time and confidence measurements;
- append-only history;
- rebuilding current state from events.

Changes that break an existing event must use a new schema version. Historical events are never rewritten to match a new contract.

## v0.5.0 learning-loop objects

Independent contracts preserve assessed event Schema 1.0:

| Contract | Role and boundary |
| --- | --- |
| `learner_identity.schema.json` | Separate stable learner identity and personal/demo mode |
| `course_package.schema.json` | Authored unit DAG and diagnostic probes; registration is not an attempt |
| `learning_model.schema.json` | Rebuildable learner-specific estimates, source audit and unvalidated status |
| `fsrs_ratings.schema.json` | Observed ease ratings linked to actual qualified events |
| `calibration_check.schema.json` | Explicitly synthetic sanity summary, never human validation |

`learning_context`, `learning_models` and `fsrs_adapter` provide standard-library
runtime validation for their inputs. Optional JSON Schema tests validate generated
reports independently. Model outputs are derived data, not assessed evidence.
