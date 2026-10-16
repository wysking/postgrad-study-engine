# Data Contracts

## Stable Objects

- Knowledge unit: 能被独立提问、测试、调度和关联先修条件的最小对象。
- Learning event: 一次有学习证据的答题、回忆、讲解、变式或诊断状态变化。
- Diagnosis: 对最早偏离点和候选根因的可修订判断。
- Derived state: 可从全部事件确定性重建的当前摘要。

正式契约位于 `schemas/`。运行时校验由 `scripts/contracts.py` 使用 Python 标准库完成，因此第一版不依赖第三方 JSON Schema 包。除学习对象外，Core 还定义了源引用、移动请求和回执契约。

## Identifier Rules

知识单元 ID 使用小写点分层级：

```text
math.calculus.limit.equivalent_substitution
english.reading.distractor.scope_expansion
materials.diffusion.ficks_first_law
```

`event_id` 对每个事件唯一；`diagnosis_id` 在同一诊断的全部修订中保持不变。

## Append-Only Rule

事件账本默认位于 `events/learning_events.jsonl`，每行一个 JSON 对象。写入前执行完整校验和重复 ID 检查。诊断状态变化追加新事件，不修改历史行。

追加时保留原文件字节前缀，包括合法 BOM、CRLF、空白和旧行格式；必要时仅补行分隔符，再写新事件。直接 reducer 调用同样检查事件身份及合法诊断修订链。estimated_minutes 必须是真正整数，不能使用 Python 中可被当作整数的布尔值。契约原已无效的数据若被发现则明确失败，不静默清洗历史。

新 confirmed/draft_check 的来源门槛见 ERROR_CLOSURE_PROTOCOL。它只校验本次待追加事件，不让新写入策略使旧版合法历史无法读取；也不重新判定已存历史或把自由文字当作真实核查证明。

常用命令：

```powershell
python -m scripts.validate_events
python -m scripts.append_event --event path\to\event.json
python -m scripts.rebuild_state
python -m scripts.build_context_capsule
```

使用 `examples/` 中的演示事件时，应通过 `--events state/local/demo_events.jsonl` 指向本地演示账本，不得把演示数据写入真实学习历史。

## Deterministic State

`scripts/rebuild_state.py` 从事件生成：

- 分知识单元的六维证据摘要；
- 正常正确、异常正确和辅助作答计数；
- 置信度校准摘要；
- 当前诊断状态；
- 仅基于 confirmed 诊断的错误模式；
- 纠错、鉴别、变式和延迟复习队列。

当前未发布分支使用 heuristic-evidence-0.2。活动只提名维度：辅助、猜测、不确定或过程未核验的正确解题不能增加 independent、transfer 或 timed 正向能力；受支持的解释仍可以保留 comprehension 增量。错误与部分作答保留负向摘要、原结果和辅助条件，不删除失败证据。

evidence_counts 仍统计观察，不是合格成功数量；新增派生 qualified_positive_counts 和 evidence_coverage 明确支持、未测及待核验目标。完整独立变式可以支持两个维度，但仍只有一条 attempt。没有实测用时的 timed_practice 不增加 timed 正向摘要。

mastery_overall 在目标未全部得到合格正向证据时为 null；含 independent 目标时还要求至少两道不同题目的完整无提示成功，其他目标至少两次无提示成功。这是保守的摘要可用性门槛，不是统计可靠性或掌握声明。剩余未测迁移、延迟和速度仍保持未知，不能从活动名称补出成功。

mastery 仍是启发式摘要，不是校准后的掌握概率。旧 1.0 事件保持不变；模型语义变化通过固定账本重放和独立 Core 发布审查，不通过改写历史实施。delayed_days 是输入声明的间隔，不是脚本已验证未再学习或未看答案的证明。

## Mobile Requests

手机请求是待核查的结构化 JSON，不是新的事件类型，也不能绕过 `process_inbox.py` 直接覆盖账本。处理器按 `MOBILE_DESKTOP_WORKFLOW.md` 核查、去重、映射知识单元，再转换为既有 1.0 事件。用时、信心和结果放在 `attempt` 中，确认错因标签放在独立 `diagnosis` 事件中。

缺失必填事实的请求失败并产生回执；不会因新增移动请求而改变历史事件格式或调度行为。
