# First-time setup · 首次接入

[简体中文首页](../README.md) · [English README](../README.en.md)

This guide covers the existing v0.4.0 local integration. It creates no hosted service and changes no contracts. First verify the fictional demo, then configure a separate empty Vault. Existing Vaults follow their own reviewed upgrade process.

本指南说明 v0.4.0 已有的本地接入方式，不新增服务或契约。先验证虚构演示，再配置独立的空白 Vault；已有 Vault 应沿用自己的升级审核流程。

## 1. Verify the Core · 验证引擎

Use Git and Python 3.12, the version exercised in CI. Run these commands in Git Bash, a typical Unix shell, or PowerShell:

使用 Git 和 CI 已验证的 Python 3.12。在 Git Bash、常见 Unix shell 或 PowerShell 中运行：

```sh
git clone --branch v0.4.0 https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m unittest discover -s tests -v
python -m scripts.validate_events
python -m unittest tests.test_cli_workflow -v
git rev-parse HEAD
```

The CLI test uses fictional data in a temporary directory and cleans it up. Passing the empty-ledger check alone does not prove that a private Vault works. For v0.4.0, the published commit is `e42d4700576c41f735f96417d55d7d0ceae98ab0`; the newer documentation on `main` is separate from that release.

CLI 测试使用临时目录中的虚构数据，结束后自动清理。空账本校验通过不代表私人 Vault 已接通。v0.4.0 发布提交为 `e42d4700576c41f735f96417d55d7d0ceae98ab0`；`main` 上后续更新的文档不等于重新发布版本。

## 2. Prepare an empty private Vault · 准备空白私人 Vault

Keep the Core checkout and Vault as separate directories. From the Core root, these commands create a **new** adjacent `private-vault` and copy only the generic scheduler configuration. Directory creation stops if `private-vault` already exists; do not run this over an existing Vault.

Core 和 Vault 使用独立目录。以下命令从 Core 根目录运行，创建一个**新的**相邻目录 `private-vault`，只复制通用调度配置。该目录已存在时创建会停止；不要对已有 Vault 执行初始化。

```sh
python -c "from pathlib import Path; from shutil import copyfile; root=Path('../private-vault'); root.mkdir(); (root/'config/personal').mkdir(parents=True); (root/'inbox').mkdir(); copyfile('config/scheduler.json', root/'config/personal/scheduler.json')"
```

Before processing, review `config/personal/scheduler.json` in your Vault. Its copied values are examples, not a personal study plan. Choose your own phase, enabled subjects, activation dates, and weights; see the [scheduler guide](GLOBAL_SCHEDULER.md). The processor prefers this file over `config/scheduler.json` if both exist.

处理请求前，检查 Vault 中的 `config/personal/scheduler.json`。复制值只是示例，不是你的学习计划。自行确定阶段、启用学科、激活日期和权重，参见[调度说明](GLOBAL_SCHEDULER.md)。两个配置路径都存在时，处理器优先采用 `config/personal/scheduler.json`。

| Vault path / 路径 | Role / 用途 |
| --- | --- |
| `engine.lock.json` | Exact runtime selection; create it in step 3 / 精确运行版本，下一步创建 |
| `config/personal/scheduler.json` | Private scheduling configuration / 私人调度配置 |
| `inbox/<request_id>.json` | Compact structured inputs / 紧凑结构化请求 |
| `state/knowledge_units.json` | Source registry; an absent file initially means no registered units / 源知识单元注册表，初始缺失表示尚未注册单元 |
| `events/learning_events.jsonl` | Append-only evidence, created when actual events are accepted / 真实事件被接收后生成的只追加账本 |
| `outbox/<request_id>.json` | Same-ID operation result / 同编号操作回执 |
| `state/derived_state.json`, `exports/latest.json`, `exports/latest.md` | Generated assessment state and readback / 生成的评估状态与读回摘要 |
| `records/study_records.jsonl`, `exports/study_records.json` | Separate compact observations and their index, if enabled / 启用轻量记录后的独立观察与索引 |

Do not seed a real Vault with fictional examples or another learner's records. Register real units through `register_unit` using the [knowledge-unit contract](../schemas/knowledge_unit.schema.json) when needed. Keep personal profiles and teaching instructions in the private integration, not the public Core.

不要用虚构示例或其他人的记录初始化真实 Vault。需要时依据[知识单元契约](../schemas/knowledge_unit.schema.json)通过 `register_unit` 注册实际单元。个人档案和教学指令由私人接入层维护，不放入公共 Core。

## 3. Pin and verify the runtime · 锁定并核验运行版本

Create `engine.lock.json` in the new Vault with these fields for v0.4.0:

在新 Vault 中创建 `engine.lock.json`；v0.4.0 的完整字段如下：

```json
{
  "repository": "wysking/postgrad-study-engine",
  "version": "v0.4.0",
  "commit": "e42d4700576c41f735f96417d55d7d0ceae98ab0",
  "event_schema": "1.0"
}
```

From the Core root:

从 Core 根目录运行：

```sh
python -m scripts.validate_engine_lock --lock ../private-vault/engine.lock.json
git rev-parse HEAD
python -c "from scripts.process_inbox import ENGINE_VERSION; print(ENGINE_VERSION)"
```

Compare the checkout SHA with the lock's `commit` and the printed engine version with `version` (without its `v` prefix). The lock validator checks field format; it does **not** fetch or switch code, verify a release, or enforce the lock inside `process_inbox`. Your launcher or workflow must check out and verify the pinned runtime before calling it. Use a separate reviewed lock upgrade for future versions.

核对当前 SHA 与锁文件的 `commit`，以及打印的引擎版本与去掉 `v` 前缀的 `version`。锁文件校验器只验证字段格式，**不会**下载或切换代码、验证发布，`process_inbox` 内部也不会自动执行锁定。启动器或工作流须先检出并核验锁定版本；未来升级单独审核。

## 4. Verify a request without adding evidence · 不新增学习证据的首次验证

For the **new empty Vault**, save the following fictional transport check as `inbox/setup-schedule-001.json`. Replace `created_at` and `as_of` together with the actual timezone-aware check time. It supplies a one-minute budget and no candidates, so the empty Vault produces a plan with no tasks; it does not claim any learning occurred. Do not copy it into an existing learner's inbox.

仅在**新建空白 Vault**中，将以下虚构接入检查保存为 `inbox/setup-schedule-001.json`。把 `created_at` 和 `as_of` 一起替换为实际检查时间，保留时区。它提供一分钟预算和空候选列表，空白 Vault 因而生成无任务计划，不声称发生过学习。不要复制到已有学习者的 inbox。

```json
{
  "schema_version": "1.0",
  "request_id": "setup-schedule-001",
  "created_at": "2026-08-10T09:00:00Z",
  "operation": "request_schedule",
  "client": "local-setup-check",
  "payload": {
    "request": {
      "schema_version": "1.0",
      "available_minutes": 1,
      "as_of": "2026-08-10T09:00:00Z",
      "candidates": []
    }
  }
}
```

Run from the Core root:

从 Core 根目录运行：

```sh
python -m scripts.process_inbox --vault-root ../private-vault --request ../private-vault/inbox/setup-schedule-001.json
```

Inspect `outbox/setup-schedule-001.json`: its ID and operation must match, with `status: "succeeded"`, the expected engine version, and a plan with `scheduled_minutes: 0` and no selected tasks. `exports/latest.json` should report `registry_count: 0` and `state.event_count: 0`. Check the request hash when possible: it is SHA-256 of UTF-8 JSON serialized with sorted keys, `ensure_ascii=False`, and separators `(',', ':')`, not a hash of the original file bytes.

读取同编号回执：编号、操作须匹配，状态为 `succeeded`，引擎版本符合预期，计划为零分钟且没有入选任务。`exports/latest.json` 应显示注册单元与事件数均为 0。能够计算时核对请求哈希：对键排序、`ensure_ascii=False`、分隔符为 `(',', ':')` 的 UTF-8 JSON 计算 SHA-256，不是对原文件字节计算。

Repeat the **unchanged** request to verify idempotency. Changing a processed request's timestamp or payload changes its identity hash and is not a retry. A local succeeded receipt proves this local check only; it does not establish remote persistence or learning evidence.

重复提交**完全不变**的请求可验证幂等性。已处理请求的时间或载荷不能在重试时改动。该本地成功回执只证明本地接入检查通过，不证明远端保存或学习证据归档。

## 5. Connect remote automation · 接入远端自动化

Local processing does not install a GitHub workflow or connect ChatGPT automatically. If you put the Vault in Git, create a **private** repository and inspect its visibility before pushing personal data. Your reviewed workflow must check out the locked Core, serialize writers across runners, and persist each operation's outputs together with its receipt. Compact records require persistence of `records`, `outbox`, and `exports`; a receipt without its associated data is insufficient. Keep the operating-system lock file `.study-inbox.lock` untracked.

本地处理不会自动安装 GitHub 工作流或连接 ChatGPT。使用 Git 托管 Vault 时，应先创建**私有**仓库并核对可见性。工作流需审核锁定 Core 的检出、跨运行器串行处理，以及数据与回执的一起保存；轻量记录要保存 `records`、`outbox` 和 `exports`。只有回执、缺少对应数据不能确认保存。`.study-inbox.lock` 不纳入版本控制。

Check remote same-ID receipts and outputs after a real operation, then refresh the matching export. Follow the [workflow](MOBILE_DESKTOP_WORKFLOW.md), [receipt and recovery rules](MOBILE_REQUESTS.md), [compact-record adoption requirements](LIGHTWEIGHT_STUDY_RECORDS.md#adoption-rollback-and-later-assessment), and [migration notes](../migrations/README.md). This guide does not supply a production workflow or change the teaching protocol.

真实操作后核对远端同编号回执及对应输出，再刷新相关导出。详细要求见[跨端工作流](MOBILE_DESKTOP_WORKFLOW.md)、[回执与恢复规则](MOBILE_REQUESTS.md)、[轻量记录采用要求](LIGHTWEIGHT_STUDY_RECORDS.md#adoption-rollback-and-later-assessment)与[迁移说明](../migrations/README.md)。本指南不提供生产工作流，也不修改教学协议。

## Troubleshooting · 常见问题

| Observation / 现象 | Meaning and next step / 含义与处理 |
| --- | --- |
| `status: idle`, `processed: 0` | No requests found; this does not validate configuration / 没有请求，不代表配置通过验收 |
| No scheduler configuration | Review the private config path in step 2 / 核对第 2 步的私人配置路径 |
| `failed` receipt or CLI exit 2 | Inspect the specific request and error; preserve failed identities and receipts for reviewed recovery / 查看具体错误，保留失败请求和回执，按流程审核恢复 |
| Same ID with conflicting hash | Original request was changed; do not overwrite history or rename it to evade failure / 请求被修改，不覆盖历史，也不换号绕过失败 |
| `pending` change request | Proposal registered for review, not a deployed change / 建议已登记，不代表变更已上线 |
| No assessment export after a compact save | Compact observations have a separate index and do not update capability state / 轻量观察使用独立索引，不更新能力状态 |
| Another writer is active | Let the writer finish and retry the unchanged request; do not delete an active lock / 等待写入者结束，原样重试，不删除活动锁 |
