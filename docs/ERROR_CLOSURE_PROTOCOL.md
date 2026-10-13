# Error Closure Protocol

本协议定义单题错误闭环。Codex 负责活的推断与变式生成；脚本负责证据契约、只追加历史、状态重建和复测排队。

## Audit Trigger

以下条件全部成立时，一道正确题按轻量证据通过，不启动诊断树：

- 答案正确；
- 草稿过程无客观异常；
- assistance level 为 0；
- learner 没有标注 guess 或 uncertain；
- learner 没有主动询问对应知识点。

答错、蒙猜、不确定、过程可疑、正确答案无法由草稿推出，或历史错误再次出现时，启动诊断。

## Diagnostic Loop

```text
题目条件与目标
-> Codex 构造合法解题路径图
-> 将答案和草稿步骤与路径图对齐
-> 定位最早偏离点
-> 区分发生点与候选根因
-> 给出带依据和置信度的候选诊断
-> learner 核查、复述或重做
-> confirmed / rejected / unresolved
-> confirmed 后生成一到两道针对性变式
-> 独立作答后安排延迟复测
```

草稿识别不清的位置必须列入 `transcription_uncertainty`，不能作为确认错因的唯一依据。

## Diagnosis State

- `hypothesized`: Codex 或 learner 提出候选错因，不能进入长期错误统计。
- `confirmed`: learner 核查或独立行为证据确认，可以进入长期统计。
- `rejected`: 候选错因被否定，从当前错误状态移除但保留历史。
- `unresolved`: 证据不足，保留待查，不降低掌握度。

同一个 `diagnosis_id` 的状态变化必须追加新事件，通过 `supersedes_event_id` 形成线性修订链，不得改写旧事件。

`hypothesized` 和 `unresolved` 的下一步仍进入按诊断、知识单元分别保留的鉴别队列，但不加入 confirmed 错误统计。同一单元的新题正确不能关闭其他诊断；清晰、独立且关联 `parent_diagnosis_id` 的成功才完成对应单元的复测任务，随后安排延迟复习。确认一次具体错误不等于已证实长期稳定错误模式。

## Error Structure

完成诊断任务还必须匹配已出现、未 rejected 的父诊断和实际受测单元。只带 parent_diagnosis_id 不构成完成证据；同一单元的 explain 正确不能替代独立求解。孤立或跨单元父引用保留历史事件，但输出警告且不关闭诊断。

明确没有 independent 目标的回忆单元，可以用无提示、过程可核查的 recall/review 完成对应检索任务，不增加独立解题计数。错题、部分作答、猜测、不确定或过程缺失需要即时核验；recommended_review_at 不能把这些问题推迟到任意未来。辅助正确仍需次日确认。

诊断尽量区分：

- `first_divergence`: 草稿或推理中最早出现的客观偏离；
- `root_cause`: 经 learner 确认的知识、策略或行为原因；
- `error_tags`: 用于跨题聚合同类错误的标签。

无法确认根因时只记录发生点，不强行解释。

## Variant Levels

- `isomorphic`: 相同结构，检查错误能否立即修复；
- `near_transfer`: 改变表述或局部结构；
- `boundary`: 改变公式或方法的适用条件；
- `mixed_transfer`: 与其他知识点组合并要求自主选法。

默认只生成一题同构题和一题近迁移或边界题。变式题应先检查条件完整、答案确定、目标单一和难度适当；可确定性计算的答案应由脚本或独立计算复核。

## Evidence Gate

一次正确只能增加相应维度的证据，不能单独宣告完全掌握。`confirmed` 错因完成变式后仍需延迟复测。掌握需要逐步覆盖理解、回忆、独立解题、迁移、延迟回忆和限时稳定。
