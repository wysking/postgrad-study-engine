# Contributing to Postgrad Study Engine · 贡献指南

Thank you for your interest in **Postgrad Study Engine** — an open-source long-term memory engine for AI tutors and long-term self-study.

感谢关注 **Postgrad Study Engine**（面向 AI 私教与长期自学的开源长期记忆引擎）。

---

## Scope & Privacy Boundary · 范围与隐私边界

- **Public Core vs. Private Vault**: This repository is the reusable **Core** (schemas, deterministic state reducer, forgetting-curve / FSRS models, constrained scheduler, CLI, and templates). Never include real personal study logs, real exam scores, target school choices, credentials, API keys, local absolute paths, or copyrighted/paid textbook scans in Issues or Pull Requests.
- **Use Fictional Data**: All tests, bug reproductions, and example payloads contributed to this repository must use clearly fictional data (like `examples/courses/fictional-14-days.json`).

---

## Local Development & Testing · 本地开发与测试

The baseline engine uses only the **Python 3.12+ standard library** (optional FSRS support is listed in `requirements-models.txt`).

```sh
# 1. Run the complete unit test suite
python -m unittest discover -s tests -v

# 2. Validate sample event ledger
python -m scripts.validate_events

# 3. Smoke-test the 14-day fictional demo in a temporary directory
python -m scripts.study demo --vault ../tmp-fictional-demo
```

Before opening a Pull Request, please verify that all existing tests pass with zero new failures.

---

## Submitting Changes · 提交流程

1. **Bug Reports & Feature Requests**: Open an issue using the templates in `.github/ISSUE_TEMPLATE/`.
2. **Pull Requests**:
   - Keep changes focused and backwards-compatible with existing `schemas/` (`1.0`).
   - Any schema-affecting change requires a corresponding migration test under `tests/`.
   - Include unit tests covering new behavior or bug fixes.

---

## Licensing · 许可说明

By contributing to this repository, you agree that:
- Code contributions are licensed under the [MIT License](LICENSE).
- Documentation, protocols, schemas, and templates are licensed under [CC BY 4.0](LICENSE-DOCS-CC-BY-4.0).
