# Global Scheduler

全局调度器在给定时间预算内，从当前复习队列、未测知识单元和调用方提供的候选任务中选择任务组合。个人阶段、权重和激活日期由 Vault 配置提供。

## Boundary

交互层负责：

- 解释题目与草稿；
- 产生候选错因；
- 生成并审核变式题；
- 判断候选任务是否符合当前真实学习情境。

确定性调度器负责：

- 执行时间、阶段学科、先修条件、疲劳和单科占比约束；
- 计算候选任务的透明优先级；
- 选择总价值较高的任务组合；
- 输出每个评分分量和未选原因。

## Objective

第一版优先级使用：

```text
预计提分 + 遗忘风险 + 信息增益 + 迁移价值
+ 紧迫度 + 错误复发
- 耗时惩罚 - 疲劳成本
```

权重位于 `config/scheduler.json`。这些值是启发式决策参数，不是经过个人数据校准的提分概率。后续应使用真实章节测试、延迟复测和模拟卷结果校准。

`model_version` 标识实际运行的调度器（`constrained-priority-0.2`）；调用方配置中的版本标签另记为 `config_model_version`。旧配置仍可使用，评分公式与权重未改变。

调度器、记忆模型和 FSRS 接入的升级路线见 `MEMORY_AND_SCHEDULING_MODEL_ROADMAP.md`。不得为了使用复杂模型而绕过数据条件、验证计划或可解释基线。

## Constraints

- `available_minutes` 必填；没有真实时间预算时不生成正式日程。
- `as_of` 必填；到期判断必须有带时区的可复现时间点。
- `phase_subjects` 控制当前阶段允许进入计划的学科。
- 未满足先修门槛的新知识单元不会入选。
- `max_subject_share` 限制多学科候选存在时单科占用比例。
- `fatigue_budget` 可选；未提供时疲劳作为软惩罚。
- `subject_activation` 可由 Vault 配置提供；在激活时间之前，候选会以 `subject_not_active` 排除。
- 任务不可切分，因此可能留下少量无法填充的时间。
- 带 `due_at` 的 `review`、`diagnostic`、`correction`、`targeted_variant` 只在到期时或之后入选，比较实际带时区的时间点。未来 review 返回 `review_not_due`，未来核验返回 `check_not_due`；辅助正确产生的次日确认不得当日入选。提前练习应明确作为 `practice`，不能据此声称完成延迟确认或延迟保持；排程不移除原队列。
- 同一单元的通用 `correction` / `diagnostic` 每次计划最多选择一项；保留其余队列和排除原因。具体诊断不因共享单元而合并。
- 调用方提供的 `learn` / `practice` / `timed_practice` 若对应已登记单元，同样检查登记的先修条件，不能用 `prerequisite_ready: true` 覆盖。纠错和诊断可用于探测先修不足。
- 没有登记的外部单元仍依赖调用方提供的资格判断；调度器不能推断不存在的知识关系。
- 候选引用已登记单元时，subject 必须与当前单元关系一致，否则以 `unit_subject_mismatch` 排除。先核对身份，再执行学科阶段、激活和时间分配限制；不自动改标签，也不推断未知单元的学科关系。

## Usage

```powershell
python -m scripts.rebuild_state
python -m scripts.schedule_global --request examples\schedule_request.json --output state/local/demo_schedule.json
```

输出默认写入 `state/current_schedule.json`，包含入选任务、时间区间、学科时间分配、评分拆解、排除原因和局限提示。

上面的命令显式写入隔离的演示输出；示例中的时间和候选任务不能充当真实日程。正式调用应使用当次请求并选择正式输出。手机未连接本地工具时只能给临时建议，不能声称已运行本调度器；跨端流程见 `MOBILE_DESKTOP_WORKFLOW.md`。

当前组合选择使用有状态上限的动态规划。它不声称获得数学意义上的全局最优解，输出中的 `optimality_claim` 固定为 `none`。

第一版不包含 FSRS 参数拟合。复习时间先使用明确、可重建的保守间隔；积累真实延迟复测事件后再接入 FSRS。
