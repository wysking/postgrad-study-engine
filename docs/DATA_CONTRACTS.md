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

当前 mastery 数值是 `heuristic-evidence-0.1` 的可解释启发式摘要，不是校准后的掌握概率。未来更换模型时，旧事件保持不变，重新生成派生状态。

## Mobile Requests

手机请求是待核查的结构化 JSON，不是新的事件类型，也不能绕过 `process_inbox.py` 直接覆盖账本。处理器按 `MOBILE_DESKTOP_WORKFLOW.md` 核查、去重、映射知识单元，再转换为既有 1.0 事件。用时、信心和结果放在 `attempt` 中，确认错因标签放在独立 `diagnosis` 事件中。

缺失必填事实的请求失败并产生回执；不会因新增移动请求而改变历史事件格式或调度行为。
