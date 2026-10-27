# First-time setup · 首次接入

[简体中文首页](../README.md) · [English README](../README.en.md)

v0.5.1 supplies a local learning entry point. Use Git and Python 3.12. It does
not install hosted automation; an existing Vault follows its own reviewed
upgrade process. / v0.5.1 提供本地学习入口；已有 Vault 单独审核升级。

## 1. Verify a clean release checkout · 验证发布检出

```sh
git clone --branch v0.5.1 https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m unittest discover -s tests -v
python -m scripts.validate_events
git rev-parse HEAD
```

These tests use fictional data. Optional FSRS requires
`python -m pip install -r requirements-models.txt`; the baseline needs only the
standard library. Tests verify software behavior, not learning effectiveness.

## 2. Run the fictional demo · 先跑虚构演示

```sh
python -m scripts.study demo --vault ../fictional-study-demo
python -m scripts.study today --vault ../fictional-study-demo --as-of 2026-08-15T09:00:00Z
```

Open `reports/demo.html` inside that demo. Its nine units and 15 events span
14 elapsed days. Independent success, assisted correction and delayed failure
remain distinct. Initialization refuses an existing destination. Do not copy
these fictional records into a real learner's archive.

打开演示目录中的 `reports/demo.html`。演示展示独立正确、辅助修正与延迟失败的区别。
真实档案使用独立空白目录，不导入演示事件。

## 3. Initialize a real empty Vault · 新建真实空白档案

```sh
python -m scripts.study init --vault ../my-private-vault
python -m scripts.study today --vault ../my-private-vault
```

The initializer creates an empty private directory, a random stable learner ID,
scheduler configuration and a lock to the actual clean checkout SHA/version.
Review `config/personal/scheduler.json` before formal scheduling: choose enabled
subjects, phase and activation dates. No actual learning is created by setup.
The CLI checks runtime identity before processing and does not fetch or upgrade
code. Do not initialize over an existing archive.

初始化自动锁定当前干净检出的真实提交和版本。检查档案中的学科、阶段与激活日期。
空档案没有学习证据；后续更换引擎需独立审核。

| Vault path | Purpose / 用途 |
| --- | --- |
| `engine.lock.json`, `learner.json` | Exact runtime and separate learner identity / 版本与独立身份 |
| `config/personal/scheduler.json` | Private scheduling choices / 私人调度配置 |
| `config/courses/*.json`, `state/knowledge_units.json` | Authored course and source registry / 课程与知识注册表 |
| `inbox/<id>.json`, `outbox/<id>.json` | Immutable request and matching receipt / 请求与同号回执 |
| `events/learning_events.jsonl` | Append-only assessed evidence / 正式证据账本 |
| `records/study_records.jsonl` | Separate unassessed observations / 独立未评估记录 |
| `state/derived_state.json`, `exports/*`, `reports/*` | Derived views / 可重建结果 |

## 4. Teach, observe and check · 教学、观察与核对

Register an authored real course with `python -m scripts.study course --vault
../my-private-vault --file YOUR_COURSE.json`. It uses the
[course contract](../schemas/course_package.schema.json); the supplied fictional
course is permitted only in a demo Vault. Registration adds no attempts.

If only an observation is known, archive only that observation:

```sh
python -m scripts.study record --vault ../my-private-vault --summary "Read an explanation; independent solving was not observed."
python -m scripts.study today --vault ../my-private-vault
python -m scripts.study tutor --vault ../my-private-vault --question "Help me reconstruct the first step"
```

The example summary must be replaced with what actually happened. Unknown
results stay unassessed. Formal recording requires the actual unit, question,
result, process, mode, assistance and timestamp. Read the
[complete guide](LEARNING_MODELS.md) for fields, optional OpenAI setup, fitting,
evaluation and local reports. The repository [teaching Skill](../skills/study-tutor/SKILL.md)
specifies the observation/receipt loop. Teaching text alone adds no evidence.

The CLI checks a matching local receipt, hash and actual stored event/record.
Use `retry --request-id ID` only for the unchanged request; preserve failures
for reviewed recovery. A local result does not prove remote persistence.

## 5. Optional remote integration · 可选远端接入

Keep learner repositories private and verify visibility before pushing personal
data. A reviewed workflow must check out the exact locked Core, serialize
writers and persist requests, actual data and corresponding receipts together.
Keep `.study-inbox.lock` untracked. Verify remote same-ID results after each
operation. Publishing a public Core release does not upgrade private Vaults.

完整远端接入要求见[跨端工作流](MOBILE_DESKTOP_WORKFLOW.md)、
[回执与恢复](MOBILE_REQUESTS.md)、[轻量记录](LIGHTWEIGHT_STUDY_RECORDS.md)与
[迁移说明](../migrations/README.md)。校准边界见[合成报告](CALIBRATION_REPORT_0_5_0.md)。
