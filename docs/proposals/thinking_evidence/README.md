# Thinking evidence proposal

**Draft, not deployed.** This directory contains a proposed observation contract,
research metric definitions and acceptance plan. It does not change active
schemas, runtime code, version metadata or scheduling behavior. All examples
and executable review fixtures are fictional.

- [契约与采集设计](DESIGN.md)
- [指标、证据等级与报告](METRICS_AND_REPORTS.md)
- [验收与发布计划](TEST_AND_ROLLOUT_PLAN.md)
- [拟议观察 Schema](observation.schema.json)
- [虚构评审用例](fictional_cases.json)
- [离线评审检查器](review_check.py)

The proposed `1.1` event is rejected by current Core. Supporting a mixed ledger,
preserving attempt sample counts, integrating receipt/recovery guarantees and
testing rollback compatibility are future reviewed implementation work. Existing
reliability fixes must be completed first.
