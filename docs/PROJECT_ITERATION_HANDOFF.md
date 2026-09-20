# Core change protocol

This document governs changes to the public engine. It is deliberately free of
learner-specific strategy, target-school information, and personal history.

## Before editing

1. Read `AGENTS.md`, the current `VERSION`, and the affected contract or code.
2. State the problem, affected contract, compatibility risk, and smallest useful change.
3. Check whether the change touches a schema, event sequence, reducer, scheduler,
   mobile request, or licensing boundary.

## Contract requirements

Every new durable object defines:

- a stable identifier;
- required and optional fields;
- allowed values and evidence levels;
- how input becomes durable evidence;
- how state is rebuilt without rewriting history;
- failure behavior when evidence or provenance is missing;
- at least one fictional example and one validation rule.

## After editing

1. Run focused tests and the complete test suite.
2. Validate JSON and JSONL examples.
3. Update `VERSION`, `CHANGELOG.md`, and migration notes when compatibility changes.
4. Scan the whole tree for personal data, credentials, absolute paths, and third-party
   source files before a release.
5. Keep production Vault updates behind a reviewed pull request.

## Iteration record template

```text
date:
change_id:
problem:
decision:
files_changed:
compatibility_notes:
verification:
remaining_risks:
```
