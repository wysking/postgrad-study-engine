# Postgrad Study Engine

[简体中文](README.md) · [English](README.en.md)

**让每天的提问，成为下一次学习的起点。**

一个面向考研与长期自学的开源 AI 学习项目：平时照常向 AI 提问，保存实际做题过程，定期回看记录，再带着对学习者的新理解继续教学。

轻量的是记录过程。题目、思路、提示、错误、修正和做题策略，实际发生了多少，就尽量保留多少有用信息。学习者专心学习，记录和后续分析各自完成。

[了解日常使用](#每天怎么用) · [运行演示](#先体验一次) · [搭建自己的档案](docs/GETTING_STARTED.md) · [配置定期复盘](docs/EVERYDAY_LEARNING.md)

[![Release](https://img.shields.io/github/v/release/wysking/postgrad-study-engine)](https://github.com/wysking/postgrad-study-engine/releases)
[![Core tests](https://github.com/wysking/postgrad-study-engine/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/wysking/postgrad-study-engine/actions/workflows/test.yml)
[![Code: MIT](https://img.shields.io/badge/Code-MIT-green)](LICENSE)
[![Docs: CC BY 4.0](https://img.shields.io/badge/Docs-CC_BY_4.0-lightgrey)](LICENSE-DOCS-CC-BY-4.0)

![Postgrad Study Engine：学习记录与长期接续](docs/assets/social-preview.jpg)

## 每天怎么用

### 1. 照常提问、做题、讨论

可以发一道题、检查自己的步骤、追问一个概念，也可以直接给出完整解法。AI 按当前问题讲解和反馈；需要时再做针对性练习。

### 2. 当场保存真实经过

一道直接做出的题，可以只有简短记录。经历了几轮尝试的题，可以保留最初构造、关键推导、接受过的提示、系数错误以及后来的理解。有真实用时就记录，没有就留空。保存前不要求补齐一份评估清单。

以下是**虚构的使用示例**：

> 今天练习复合函数求导，最初漏乘内层导数。AI 提醒链式法则后，我补上了这一项，重新计算得到正确结果。用时没有记录。

这已经是一条有价值的学习记录。提示后的正确会按实际经过保存。

### 3. 定期回看，更新对学习者的理解

配置独立的 GPT 复盘后，它可以阅读累积记录，关联同一道题的不同阶段，整理近期进步、反复出现的问题和仍需观察的地方，更新一份有来源依据的文字学习画像。复盘可以按每天或其他适合自己的周期运行。

### 4. 下次带着上下文继续

新对话读取最新画像和当前问题需要的记录。AI 据此选择更合适的解释、提示或复习内容；学习者随时可以纠正它。原始记录继续保留，后续判断可以修订。

[日常使用与复盘配置](docs/EVERYDAY_LEARNING.md)说明了如何把这些环节接起来。

## 记录、画像和数值模型分别做什么

| 部分 | 保存或生成什么 | 什么时候使用 |
| --- | --- | --- |
| 学习记录 | 真实题目背景、实际步骤、提示、错误、修正，以及已知的时间等信息 | 平时随手保存；内容可以简短，也可以详细 |
| GPT 文字画像 | 对多条记录的关联理解、近期表现、教学建议和待验证判断 | 单独复盘；供后续对话参考 |
| 正式事件与数值模型 | 满足评估契约的作答证据、可重建状态、记忆与技能参考 | 需要正式评估、模型分析或调度时使用 |

**保存记录不依赖分析成功。** GPT 画像和数值模型分别运行；当前数值模型主要读取正式事件，开放记录不会自动变成掌握度分数。一次提示后做对，也不会被记成独立完成或长期掌握。

## 这个仓库提供什么

公开的 **Core** 提供通用工具，每位使用者自己的 **Vault** 保存私人学习资料。二者分开，可以在更换设备或交互工具时继续使用自己的档案。

| 能力 | 当前状态 |
| --- | --- |
| 开放式事实记录 | 已实现；通过 `save_study_record` 独立保存，无需完整评估 |
| 正式学习证据与状态重建 | 已实现；区分独立作答、辅助表现和诊断证据 |
| 重复请求处理与保存确认 | 已实现；由工具和工作流处理，日常成功确认可以简短显示“已记录” |
| 本地演示、命令行和 HTML 报告 | v0.5.0 已提供 |
| 课程先修关系与针对性探针 | 已提供契约和示例；实际覆盖取决于配置的课程 |
| 记忆拟合、可选 FSRS 与技能参考 | v0.5.0 实验能力；真实学习效果和人群校准待验证 |
| 定期 GPT 阅读记录并更新文字画像 | 提供[接入方案](docs/EVERYDAY_LEARNING.md)；需在自己的 AI 与存储环境单独配置 |

当前发布版本是 [v0.5.0](https://github.com/wysking/postgrad-study-engine/releases/tag/v0.5.0)。本仓库提供 Python 工具、文档和集成方式；账号服务、GitHub 云端归档和定时 GPT 任务需要各自接入。下载代码不会自动开启这些服务。

## 先体验一次

需要 Git 和 Python 3.12。基础运行使用 Python 标准库。

```sh
git clone --branch v0.5.0 https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m scripts.study demo --vault ../fictional-study-demo
```

打开演示目录中的 `reports/demo.html`，可以看到一段跨 14 天的**虚构学习经历**：独立正确、提示后修正、后续失败和复测各有记录。首次运行使用不存在的目标目录；演示拒绝覆盖已有目录。

演示展示 Core 的记录与模型行为。它没有运行云端 GPT 复盘，也没有导入任何真实学习者的数据。

## 搭建自己的学习档案

从[首次接入指南](docs/GETTING_STARTED.md)建立空白私人 Vault，再选择适合自己的使用方式：

- **本地使用**：用 CLI 保存记录、查看状态和生成报告。
- **日常对话使用**：将 AI 交互工具连接到自己的存储与归档工作流，正常教学时保存实际经过。
- **定期复盘**：给独立 GPT 任务读取记录、更新分析文件的权限，设置周期；后续对话读取最新画像。

云端复盘需要执行环境能在后台调用模型并访问私人仓库。如果使用本地任务，电脑需要在任务运行时可用。具体接入、权限和首次试运行方法见[日常使用指南](docs/EVERYDAY_LEARNING.md)。

## 常见问题

### 每道题都要记录用时、信心、错因吗？

不需要。保存实际知道的内容即可。AI 可以从对话中整理事实，不应为了归档追问一堆字段，也不能替你补造缺失的信息。

### 记录详细过程，会不会拖慢平时学习？

记录沿用已经发生的学习内容。直接完成就简记，有多轮推导就尽量保留关键过程。分析放在独立复盘中；分析失败也不影响已经保存的记录。请求编号等技术细节由集成处理，具体契约放在开发文档中。

### GPT 会自动理解所有保存的记录吗？

仅仅保存不会触发理解。需要给复盘任务接入原始记录，设置明确的阅读范围和输出位置；后续对话也要读取更新后的画像。这个流程需要单独配置，模型判断仍可能出错。

### 有了文字画像，掌握度分数也会自动更新吗？

不会。文字画像提供可修订的教学理解；正式数值评估有自己的证据条件和计算入口。它们可以参考同一段学习经历，但不会把同一题的草稿、提示和修正当成多次独立成功。

### 适用于考研以外的学习吗？

考研是项目的起点。记录与复盘方式也可用于长期自学；具体课程、学科关系、题目来源和学习计划由使用者配置。公开仓库不附带完整题库。

### 已经证明能提分了吗？

尚未证明。测试和虚构演示验证软件行为；[合成校准报告](docs/CALIBRATION_REPORT_0_5_0.md)不代表真实人群验证。记忆和技能输出目前是教学参考。

## 面向开发者

通用 Core 保持可复用，个人资料、真实记录和衍生画像留在各自的私人 Vault。历史学习事件只追加，状态可以重建；引擎升级通过精确版本锁定独立采用。

| 想了解什么 | 文档入口 |
| --- | --- |
| 普通学习与定期复盘如何连接 | [日常使用与复盘](docs/EVERYDAY_LEARNING.md) |
| 初始化、演示和本地使用 | [首次接入](docs/GETTING_STARTED.md)、[学习工具与模型](docs/LEARNING_MODELS.md) |
| 云端归档、请求与持久化 | [跨端工作流](docs/MOBILE_DESKTOP_WORKFLOW.md)、[移动请求](docs/MOBILE_REQUESTS.md)、[开放记录契约](docs/LIGHTWEIGHT_STUDY_RECORDS.md) |
| 正式证据、课程与模型 | [数据契约](docs/DATA_CONTRACTS.md)、[Schema](schemas/README.md)、[全局调度](docs/GLOBAL_SCHEDULER.md) |
| 发布历史和研究方向 | [CHANGELOG](CHANGELOG.md)、[模型路线图](docs/MEMORY_AND_SCHEDULING_MODEL_ROADMAP.md) |
| 维护与贡献 | [AGENTS.md](AGENTS.md)、[变更流程](docs/PROJECT_ITERATION_HANDOFF.md) |

欢迎通过 [Issues](https://github.com/wysking/postgrad-study-engine/issues) 和 [Pull Requests](https://github.com/wysking/postgrad-study-engine/pulls) 提出问题与贡献。复现材料请使用虚构数据，个人档案和第三方付费资料留在私人存储中。

代码采用 [MIT](LICENSE)，文档、协议、Schema 和模板采用 [CC BY 4.0](LICENSE-DOCS-CC-BY-4.0)。第三方资料的权利见 [NOTICE](NOTICE.md)。
