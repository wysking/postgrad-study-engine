# Schema migrations

Historical learning events are immutable. When a contract must break:

1. add a new schema version and a documented migration;
2. write a fixture proving old data remains readable;
3. rebuild derived state from the original ledger in an isolated workspace;
4. update the Core version and changelog;
5. let each Vault update its lock through a reviewed pull request.

Never rewrite production history in place and never let a failed migration
replace the current Vault state.
