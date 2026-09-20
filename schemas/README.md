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
