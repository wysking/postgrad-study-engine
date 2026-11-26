# Lightweight AnkiWeb Read-Only Sync (`AnkiDroid + FSRS → Private Vault`)

Let **AnkiDroid (FSRS)** handle high-frequency flashcard scheduling on your phone while feeding daily review counts and stubborn words (`Again` / `lapses >= 3`) back into your private Git Vault (`save_study_record`, `Schema 1.0`) — **with zero always-on PC and zero exposure of private mnemonic fields**.

---

## 设计要点 · Key Design Principles

1. **单向只读拉取（`upload=False`）**：GitHub Actions 在夜间避开整点拥堵（例如 `23:37` 与 `00:43`，均早于 `02:00` AI 每日复盘）在临时目录拉取一次 AnkiWeb 最新进度，并默认回看最近 2 个学习日（即使 Actions 调度延迟跨过 `04:00` 换日线也不会漏掉前一晚复习）；**绝不向 AnkiWeb 回写**，零可能覆盖手机端复习状态。
2. **三栏模板字段隔离（`Word | Exam_Meaning | Private_Hook`）**：
   - 脚本仅读取第 0 栏（`Word`）与第 1 栏（`Exam_Meaning` 核心释义），自然忽略第 2 栏（`Private_Hook` 个人自由联想/重口谐音助记），跑完即删临时 `.anki2` 文件——既防敏感词触发云端大模型安全过滤，也不让大体积牌组二进制进 Git。
3. **无复习零打扰 & 幂等防重**：当天 `revlog` 无点击直接静默退出；同一天相同点击数重复运行自动跳过，不产生重复 `inbox/` 提交。

## 快速接入 · Quick Setup

1. 将 [`sync_anki_vocab.py`](sync_anki_vocab.py) 放入私有 Vault 的 `.github/scripts/sync_anki_vocab.py`，并配置 `01:00` 定时工作流（与 `process-inbox.yml` 共享 `vault-inbox` 并发锁，拉取写出 `inbox/anki-*.json` 后直接调用 `publish_inbox.py` 落盘）。
2. 在本地一次性通过官方 `anki` 库 `col.sync_login(email, password, None)` 换取 `ANKI_SYNC_HKEY` 与 `ANKI_SYNC_ENDPOINT`，存入私有 Vault 的 **GitHub Actions Secrets**（不存明文密码）。
3. 手机端 `AnkiDroid` 开启 **自动同步** 与 **FSRS**；日常刷词对卡壳词点红旗（`flag:1`）批量补充个人助记，夜间自动将顽固易忘词同步进 AI 私教上下文，在次日真题长难句拆解中靶向复现。
