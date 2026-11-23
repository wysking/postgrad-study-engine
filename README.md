<div align="center">

<img src="docs/assets/social-preview.jpg" alt="Postgrad Study Engine — Long-term memory engine for AI tutors (Kaoyan, FSRS, Spaced Repetition)" width="100%" />

# Postgrad Study Engine — Long-term Memory Engine for AI Tutors

**给 AI 私教装上可追溯的长期记忆：专为推导与深度自学打造的 Anki Alternative（考研 Kaoyan · FSRS · Spaced Repetition）**

<sub>Keywords: <b>AI Tutor</b> · <b>Long-term Memory</b> · <b>FSRS</b> · <b>Spaced Repetition</b> · <b>Anki Alternative</b> · <b>Kaoyan (考研)</b></sub>

<br />

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/wysking/postgrad-study-engine/blob/main/demo.ipynb)
[![Release](https://img.shields.io/github/v/release/wysking/postgrad-study-engine?style=flat-square&color=C83E2B&labelColor=1C1C1E)](https://github.com/wysking/postgrad-study-engine/releases)
[![Core Tests](https://img.shields.io/github/actions/workflow/status/wysking/postgrad-study-engine/test.yml?branch=main&style=flat-square&label=Core%20Tests&labelColor=1C1C1E)](https://github.com/wysking/postgrad-study-engine/actions/workflows/test.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12%20%C2%B7%20Zero%20Deps-3776AB?style=flat-square&labelColor=1C1C1E)](scripts/study.py)
[![Code: MIT](https://img.shields.io/badge/Code-MIT-2E7D32?style=flat-square&labelColor=1C1C1E)](LICENSE)
[![Docs: CC BY 4.0](https://img.shields.io/badge/Docs-CC%20BY%204.0-555555?style=flat-square&labelColor=1C1C1E)](LICENSE-DOCS-CC-BY-4.0)

**简体中文** · [English](README.en.md) · [Colab 在线体验](https://colab.research.google.com/github/wysking/postgrad-study-engine/blob/main/demo.ipynb) · [双 AI 接入（Gemini / ChatGPT）](docs/AI_INTEGRATIONS.md) · [架构与技术文档](docs/ARCHITECTURE_OVERVIEW.md) · [贡献指南](CONTRIBUTING.md)

</div>

---

> **一句话痛点**：用 AI 刷题最怕“聊完就忘、换个窗口一切归零”，传统背卡工具（Anki）又装不下数学推导的卡点与提示过程——本项目把每一次真实解题、错因与提示沉淀进私有 Git 账本，驱动 **FSRS / 半衰期遗忘曲线** 与 **每日学习画像**，让 AI 私教真正记住你会什么、卡在哪。

<div align="center">

<img src="docs/assets/demo.png" alt="Postgrad Study Engine 14-day demo report (fictional-14-days): knowledge unit status, evidence gaps, FSRS/half-life memory fit, and targeted probes" width="96%" />

<sub>▲ 运行内置 <code>fictional-14-days</code> 示例生成的真实本地报告（<code>demo.html</code> 实测截图）</sub>

</div>

## ⚡ 三行跑通（或点击顶部 [Open in Colab](https://colab.research.google.com/github/wysking/postgrad-study-engine/blob/main/demo.ipynb) 零安装体验）

```sh
git clone https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m scripts.study demo --vault ../study-demo
```

打开生成的 `../study-demo/reports/demo.html` 即可查看上方完整报告（纯 Python 3.12 标准库运行，零第三方依赖、无需 API Key）。

> ⭐ **如果你也希望 AI 私教能跨对话记住你的推导卡点与遗忘曲线，欢迎给仓库点个 Star 支持！**

---

## 🧩 为什么选它作为 AI 学习底座？

| 维度 | 普通 AI 聊天窗口 | 传统闪卡（Anki） | Postgrad Study Engine |
| :--- | :--- | :--- | :--- |
| **长期记忆 (Long-term Memory)** | 散落在几十个聊天窗口，换窗口即失忆 | 只有正反面死记硬背，无推导上下文 | Git 账本持续累积，每次开聊自动载入最新 `learner_context.md` |
| **记录负担** | 手工整理笔记耗时，不记又全流失 | 制卡成本高，难以记录多步解题思路 | 对话中顺手 `save_study_record`，简题一句话、难题保留完整提示链 |
| **间隔重复 (Spaced Repetition)** | 无遗忘追踪，全靠自己想起来才问 | 仅按主观按键排程，不懂你卡在哪一步 | 严格区分**独立做出**与**提示完成**，结合半衰期拟合 / 可选 **FSRS** 精准排程 |
| **数据主权与跨平台** | 锁死在单一平台 | 本地数据库同步受限 | **公开 Core + 私有 Vault** 分离，支持本地 CLI 与 Google Drive / Gmail 云端同步 |

---

## 🔌 两套开箱即用的云端 AI 接入方案（Gemini & ChatGPT / Codex）

同一份私有 Git 记忆账本，同时提供 **Gemini** 与 **ChatGPT / Codex** 两套完整云端接入蓝图，换模型不断档、记忆永久归你：

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🌐 方案 A：Gemini 原生全谷歌桥接（零远程 MCP）</h3>
      <p><b>Google Drive 只读镜像 + Gmail 草稿 + Google Apps Script V8 → GitHub Actions</b></p>
      <ul>
        <li>复用 Google AI Pro 原生 Gemini 聊天与 02:00 定时复盘，<b>零付费 API</b></li>
        <li>彻底告别易断连的第三方远程 GitHub MCP，零 GCP 绑卡、零公网 <code>doPost</code></li>
        <li>内置 Drive v3 原地快写（大文档不超时）、单仓 Fine-Grained PAT、本地 Schema 校验与 11 项 Node.js 测试</li>
      </ul>
      <p>👉 <a href="integrations/google-native-bridge/"><b>直接复制全套桥接代码与提示词 →</b></a></p>
    </td>
    <td width="50%" valign="top">
      <h3>🤖 方案 B：ChatGPT / OpenAI / Codex 直连接入</h3>
      <p><b>ChatGPT（GitHub 连接器 / Scheduled）· Codex CLI → GitHub Actions</b></p>
      <ul>
        <li>直接加载仓库内置私教 Skill，通过结构化 <code>inbox/&lt;request_id&gt;.json</code> 归档并核验同 ID <code>outbox</code> 回执</li>
        <li>支持配置每日定时 GPT 定性复盘任务，自动串联同题多轮记录并更新 <code>analysis/learner_context.md</code></li>
        <li>同样兼容纯本地 CLI（<code>python -m scripts.study</code>），离线可用</li>
      </ul>
      <p>👉 <a href="docs/AI_INTEGRATIONS.md"><b>查看双生态完整对比与接入指南 →</b></a></p>
    </td>
  </tr>
</table>

---

## 📚 深入了解与文档导航

完整技术细节、双生态接入代码、三层记忆架构与 FAQ 已全部收录在 `docs/` 与 `integrations/` 目录中：

- **[双生态 AI 接入方案（Gemini + ChatGPT / Codex）](docs/AI_INTEGRATIONS.md)** · **[Google 原生桥接源码与一键部署包](integrations/google-native-bridge/)**
- **[架构与技术详述（原首页完整技术内容）](docs/ARCHITECTURE_OVERVIEW.md)**：四步闭环流程图、三层数据职责、v0.5.1 能力矩阵与完整 FAQ
- **[首次接入指南](docs/GETTING_STARTED.md)**：3 分钟初始化空白私有 Vault 与本地 CLI 常用命令
- **[日常使用与云端定期复盘](docs/EVERYDAY_LEARNING.md)**：接入日常 AI 对话、夜间自动复盘与 `learner_context.md` 画像更新
- **[学习模型、遗忘曲线与 FSRS](docs/LEARNING_MODELS.md)** · **[全局约束调度器](docs/GLOBAL_SCHEDULER.md)** · **[v0.5.0 校准报告](docs/CALIBRATION_REPORT_0_5_0.md)**
- **[跨端同步工作流](docs/MOBILE_DESKTOP_WORKFLOW.md)** · **[移动请求协议](docs/MOBILE_REQUESTS.md)** · **[开放记录规范](docs/LIGHTWEIGHT_STUDY_RECORDS.md)** · **[数据契约与 Schema](docs/DATA_CONTRACTS.md)**
- **[贡献指南 (CONTRIBUTING.md)](CONTRIBUTING.md)** · **[变更日志 (CHANGELOG.md)](CHANGELOG.md)** · **[开发规范 (AGENTS.md)](AGENTS.md)**

---

<div align="center">

代码基于 [MIT](LICENSE) 开源 · 文档、协议与 Schema 基于 [CC BY 4.0](LICENSE-DOCS-CC-BY-4.0) 许可 · 第三方署名见 [NOTICE.md](NOTICE.md)

</div>
