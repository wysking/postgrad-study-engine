# Postgrad Study Engine

[简体中文](README.md) · [English](README.en.md)

**让每一次提问与推导，都沉淀为下一次学习的起点。**

面向考研与长期自学的开源 AI 学习引擎：日常照常向 AI 提问、做题、讨论，真实学习过程自动沉淀到私有 Git 账本，定期生成带溯源引用的学习画像，并按需驱动遗忘曲线与优先级调度。

[核心特性](#核心特性) · [工作闭环](#工作闭环) · [快速体验](#1-分钟快速体验) · [搭建私人档案](docs/GETTING_STARTED.md) · [日常与云端接入](docs/EVERYDAY_LEARNING.md)

[![Release](https://img.shields.io/github/v/release/wysking/postgrad-study-engine)](https://github.com/wysking/postgrad-study-engine/releases)
[![Core tests](https://img.shields.io/github/actions/workflow/status/wysking/postgrad-study-engine/test.yml?branch=main&label=Core%20tests)](https://github.com/wysking/postgrad-study-engine/actions/workflows/test.yml)
[![Code: MIT](https://img.shields.io/badge/Code-MIT-green)](LICENSE)
[![Docs: CC BY 4.0](https://img.shields.io/badge/Docs-CC_BY_4.0-lightgrey)](LICENSE-DOCS-CC-BY-4.0)

![Postgrad Study Engine：学习记录与长期接续](docs/assets/social-preview.jpg)

## 核心特性

- **无感记录，保留真实思考**：日常以开放式记录（`save_study_record`）为主，无需填写繁琐表单——简单题一句话记完，复杂推导完整保留最初思路、提示顺序、错因与修正。
- **Core 与 Vault 彻底分离**：本仓库提供公开可复用的引擎、Schema、调度器与工作流；个人笔记、原始账本与学习画像全部保存在你自己的私有 Vault 仓库中，换设备、换 AI 工具也不丢长期记忆。
- **全云端、零服务器闭环**：支持纯本地 CLI，也可配合私有 GitHub Actions 与原生云端桥接（如 Google Drive 只读镜像 + Gmail 草稿 + Apps Script 定时同步），在手机端随时学习、自动归档并完成夜间定性复盘，无需自建公网服务或额外付费大模型 API。
- **可追溯、可重建的工程底座**：底层账本采用 append-only 设计，内置幂等去重、同 ID 回执核验与确定性状态重建，并提供遗忘曲线拟合、FSRS 参数支持与多学科约束调度。

## 工作闭环

```text
  日常对话学习（手机 / 桌面 AI）
        │
        ▼  自然保存真实过程（save_study_record / 结构化事件）
  私有 Git Vault（inbox → Actions 单写入校验 → append-only 账本 + outbox 回执）
        │
        ├──▶ 定期定性复盘：串联同题多轮记录，更新带原文引用的学习画像（learner_context.md）
        └──▶ 确定性建模与调度：重建知识单元状态、生成复习队列与可视化 HTML 报告
        │
        ▼  同步最新画像与状态上下文
  下一次对话带着上下文直接衔接
```

### 三层数据各司其职

| 层级 | 保存与产出内容 | 典型场景 |
| --- | --- | --- |
| **开放式学习记录** (`records/study_records.jsonl`) | 题目背景、真实步骤、提示经过、错因与修正、已知时间 | 日常随手记录，零心智负担 |
| **定性学习画像** (`analysis/learner_context.md` / `daily/`) | 跨记录的阶段进展、易错模式、有效讲解方式与待观察项 | 每日或每周定时复盘，供下次对话直接读取 |
| **正式证据与模型** (`events/` / `state/` / `exports/`) | 结构化作答与诊断事件、六维证据摘要、遗忘风险与优先级排程 | 阶段诊断、针对性变式训练与全局复习规划 |

> **记录与分析彻底解耦**：保存事实不依赖后续分析完成；提示后做对与独立完成在底层严格区分，让长期反馈更贴近真实掌握情况。

## 1 分钟快速体验

仅需 Git 与 Python 3.12（核心引擎零第三方依赖，纯标准库运行）：

```sh
git clone --branch v0.5.1 https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m scripts.study demo --vault ../study-demo
```

打开生成的 `../study-demo/reports/demo.html`，即可浏览一份跨 14 天的示例学习轨迹，直观看到独立求解、提示后修正、错因诊断、状态重建与复习排程的完整效果。

## 接入方式

参照 [首次接入指南](docs/GETTING_STARTED.md) 初始化你的私有 Vault 后，可按需选择工作方式：

- **本地 CLI 模式**：直接通过 `python -m scripts.study` 保存记录、查看今日建议并导出 HTML 报告。
- **云端移动闭环**：通过私有 Vault 的 GitHub Actions 自动处理 `inbox/*.json` 并返回同 ID 回执；搭配 Google Drive / Gmail + Apps Script 定时桥接即可实现手机端原生 AI 对话与自动入库。
- **定时定性复盘**：配置独立定时任务按周期阅读累积账本，生成每日复盘并刷新 `analysis/learner_context.md`，下次开聊自动衔接。

完整配置步骤见 [日常使用与复盘指南](docs/EVERYDAY_LEARNING.md)。

## 能力一览（v0.5.1）

| 模块 | 能力说明 |
| --- | --- |
| 开放式记录 | `save_study_record` 轻量入库，支持自由文本、学科标签、主题与来源引用 |
| 正式证据与诊断闭环 | 区分独立作答、辅助完成与诊断状态流转，支持同构 / 迁移变式检验 |
| 跨端请求协议 | 9 类标准 `inbox` 操作，幂等去重、单写入者并发保护与 `outbox` 精确回执 |
| 模型与调度 | 确定性状态重建、多学科约束优先级调度，以及可选遗忘曲线拟合与 FSRS 模块 |
| 可视化与工具链 | 命令行入口、上下文胶囊导出、独立 HTML 学习仪表盘与完整自动化测试套件 |

## 文档导航

| 主题 | 入口 |
| --- | --- |
| 上手与日常闭环 | [首次接入指南](docs/GETTING_STARTED.md) · [日常使用与复盘](docs/EVERYDAY_LEARNING.md) |
| 跨端同步与请求契约 | [跨端工作流](docs/MOBILE_DESKTOP_WORKFLOW.md) · [移动请求协议](docs/MOBILE_REQUESTS.md) · [开放记录规范](docs/LIGHTWEIGHT_STUDY_RECORDS.md) |
| 数据模型与调度引擎 | [数据契约](docs/DATA_CONTRACTS.md) · [Schema 目录](schemas/README.md) · [学习模型说明](docs/LEARNING_MODELS.md) · [全局调度](docs/GLOBAL_SCHEDULER.md) |
| 版本与协作 | [变更日志](CHANGELOG.md) · [模型路线图](docs/MEMORY_AND_SCHEDULING_MODEL_ROADMAP.md) · [开发规范](AGENTS.md) |

## 参与贡献与许可

欢迎通过 [Issues](https://github.com/wysking/postgrad-study-engine/issues) 交流想法或提交 [Pull Requests](https://github.com/wysking/postgrad-study-engine/pulls)。

代码采用 [MIT](LICENSE) 许可，文档、协议与 Schema 采用 [CC BY 4.0](LICENSE-DOCS-CC-BY-4.0) 许可；第三方署名信息见 [NOTICE.md](NOTICE.md)。
