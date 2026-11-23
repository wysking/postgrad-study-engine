<div align="center">

<img src="docs/assets/social-preview.jpg" alt="Postgrad Study Engine — Long-term memory engine for AI tutors (Kaoyan, FSRS, Spaced Repetition)" width="100%" />

# Postgrad Study Engine

### Long-term Memory Engine for AI Tutors

<sub>面向考研（Kaoyan）与深度自学的开源 <b>AI Tutor</b> 长期记忆底座 · 支持 <b>FSRS</b> / 半衰期遗忘曲线与 <b>Spaced Repetition</b> · 专为推导与错因追踪打造的 <b>Anki Alternative</b></sub>

<br />

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/wysking/postgrad-study-engine/blob/main/demo.ipynb)
[![Release](https://img.shields.io/github/v/release/wysking/postgrad-study-engine?style=flat-square&color=C83E2B&labelColor=1C1C1E)](https://github.com/wysking/postgrad-study-engine/releases)
[![Core Tests](https://img.shields.io/github/actions/workflow/status/wysking/postgrad-study-engine/test.yml?branch=main&style=flat-square&label=Core%20Tests&labelColor=1C1C1E)](https://github.com/wysking/postgrad-study-engine/actions/workflows/test.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12%20%C2%B7%20Zero%20Deps-3776AB?style=flat-square&labelColor=1C1C1E)](scripts/study.py)
[![License](https://img.shields.io/badge/License-MIT%20%2F%20CC%20BY%204.0-2E7D32?style=flat-square&labelColor=1C1C1E)](LICENSE)

<br />

**简体中文** · [English](README.en.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Colab 在线体验](https://colab.research.google.com/github/wysking/postgrad-study-engine/blob/main/demo.ipynb) · [双 AI 接入（Gemini / ChatGPT）](docs/AI_INTEGRATIONS.md) · [完整架构](docs/ARCHITECTURE_OVERVIEW.md) · [贡献指南](CONTRIBUTING.md)

</div>

---

> **用 AI 刷题最可惜的不是“没听懂”，而是换个聊天窗口一切归零；传统背卡工具（Anki）又装不下数学推导的卡点与提示过程。**  
> Postgrad Study Engine 把你每一次真实做题、提示顺序与错因沉淀进私有 Git 账本，驱动 **FSRS / 半衰期遗忘曲线** 与 **每日学习画像**，让 AI 私教真正记住你会什么、卡在哪。

<div align="center">

<img src="docs/assets/demo.png" alt="Postgrad Study Engine 14-day demo dashboard (fictional-14-days): fitted forgetting curves, AI closed-book probes, prioritized due work, and knowledge unit mastery" width="100%" />

<sub>▲ 运行内置 <code>fictional-14-days</code> 示例生成的真实本地仪表盘（<code>reports/demo.html</code> 零 JS 实测输出）</sub>

</div>

## ⚡ 3 行跑通（或点 [Open in Colab](https://colab.research.google.com/github/wysking/postgrad-study-engine/blob/main/demo.ipynb) 零安装体验）

```sh
git clone https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m scripts.study demo --vault ../study-demo
```

打开生成的 `../study-demo/reports/demo.html` 即可看到上方完整仪表盘（纯 Python 3.12 标准库运行，零第三方依赖、无需 API Key）。

> ⭐ **如果你也厌倦了每次开新窗口 AI 就把你的薄弱点忘光，欢迎点个 Star 支持这个开源记忆底座！**

---

## 💬 Day 1 → Day 14：有长期记忆的 AI 私教有什么不一样？

<table>
  <thead>
    <tr>
      <th width="50%">❌ 普通 AI 聊天窗口（第 14 天重开新对话）</th>
      <th width="50%">✅ 接入 Postgrad Study Engine（自动载入画像 + 遗忘曲线）</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td valign="top">
        <p><b>你</b>：帮我出两道极限复习题。</p>
        <p><b>AI</b>：好的！这里有两道常见极限练习题：1. 求 <code>lim(x→0) (e^x - 1)/x</code>；2. 求 <code>lim(x→∞) (1 + 1/x)^x</code>……</p>
        <p><sub>⚠️ 完全不知道你 4 天前做 <code>sin(x)/x</code> 漏了弧度制条件，也不知道你早已熟练掌握常规等价替换。</sub></p>
      </td>
      <td valign="top">
        <p><b>你</b>：帮我出两道极限复习题。</p>
        <p><b>AI</b>：你的「标准极限闭卷回忆」拟合半衰期仅 <b>2.7 天</b>（今天留存率已降到 30% 以下），且 4 天前在角度单位条件上卡过壳。先闭卷做这道 3 分钟诊断探针：<i>写出 x→0 时 sin(x)/x 的极限及角度单位条件</i>，答完我们再推进相减消去边界。</p>
        <p><sub>✨ 精准衔接上次卡点，区分「独立做出」与「提示后做对」，拒绝虚假掌握。</sub></p>
      </td>
    </tr>
  </tbody>
</table>

---

## 🔌 两套开箱即用的云端 AI 接入方案（Gemini & ChatGPT / Codex）

同一份私有 Git 记忆账本（`Schema 1.0`），同时提供 **Gemini** 与 **ChatGPT / Codex** 两套完整云端蓝图——换设备、换主力模型，长期记忆始终连续：

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🌐 方案 A：Gemini 原生全谷歌桥接（零远程 MCP）</h3>
      <p><b>Google Drive 只读镜像 + Gmail 草稿 + Google Apps Script V8 → GitHub Actions</b></p>
      <ul>
        <li>复用 Google AI Pro 原生 Gemini 聊天与 02:00 定时复盘，<b>零付费 API</b></li>
        <li>彻底告别易断连的第三方远程 GitHub MCP，零 GCP 绑卡、零公网 <code>doPost</code></li>
        <li>内置 Drive v3 原地快写（大文档 2–3 秒不超时）、单仓 PAT、本地 Schema 校验与 11 项 Node.js 测试</li>
      </ul>
      <p>👉 <a href="integrations/google-native-bridge/"><b>复制全套桥接代码与提示词 →</b></a></p>
    </td>
    <td width="50%" valign="top">
      <h3>🤖 方案 B：ChatGPT / OpenAI / Codex 直连接入</h3>
      <p><b>ChatGPT（GitHub 连接器 / Scheduled）· Codex CLI → GitHub Actions</b></p>
      <ul>
        <li>直接加载仓库内置 <code>skills/study-tutor/SKILL.md</code>，结构化提交 <code>inbox/&lt;request_id&gt;.json</code> 并核验 <code>outbox</code> 回执</li>
        <li>支持配置每日定时 GPT 定性复盘任务，串联同题多轮推导并刷新 <code>analysis/learner_context.md</code></li>
        <li>同时支持纯本地 CLI（<code>python -m scripts.study</code>），完全离线运行</li>
      </ul>
      <p>👉 <a href="docs/AI_INTEGRATIONS.md"><b>查看双生态完整对比与接入指南 →</b></a></p>
    </td>
  </tr>
</table>

---

## 🧩 为什么它比普通聊天记录和传统闪卡更适合深度学习？

| 维度 | 普通 AI 聊天窗口 | 传统闪卡（Anki） | Postgrad Study Engine |
| :--- | :--- | :--- | :--- |
| **长期记忆 (Long-term Memory)** | 散落在几十个窗口，换窗口即失忆 | 只有孤立正反面，无推导上下文 | Append-only Git 账本 + 自动更新 `learner_context.md` |
| **记录负担** | 手写复盘太耗时，不记全流失 | 制卡成本极高，难装多步证明 | 对话中顺手 `save_study_record`，保留完整提示与修正链 |
| **间隔重复 (Spaced Repetition)** | 无遗忘追踪，全靠临时想起 | 仅按主观按键排程，不懂卡在哪步 | 区分**独立求解**与**提示完成**，拟合半衰期 / 可选 **FSRS** |
| **数据主权与跨平台** | 锁死在单一平台 | 封闭本地牌组库 | **公开 Core + 私有 Git Vault**，纯文本永久归你 |

---

## 📚 文档与架构导航

| 主题 | 入口 |
| :--- | :--- |
| **双生态 AI 接入（Gemini / ChatGPT）** | [双生态接入总览](docs/AI_INTEGRATIONS.md) · [Google 原生桥接源码包](integrations/google-native-bridge/) |
| **架构详述与快速上手** | [完整架构与 FAQ](docs/ARCHITECTURE_OVERVIEW.md) · [首次接入指南](docs/GETTING_STARTED.md) · [日常学习与定期复盘](docs/EVERYDAY_LEARNING.md) |
| **遗忘曲线、FSRS 与调度引擎** | [学习模型与 FSRS](docs/LEARNING_MODELS.md) · [全局约束调度器](docs/GLOBAL_SCHEDULER.md) · [v0.5.0 校准报告](docs/CALIBRATION_REPORT_0_5_0.md) |
| **协议契约与社区协作** | [数据契约](docs/DATA_CONTRACTS.md) · [移动请求协议](docs/MOBILE_REQUESTS.md) · [贡献指南](CONTRIBUTING.md) · [CHANGELOG](CHANGELOG.md) |

---

<div align="center">

<sub>代码基于 <a href="LICENSE">MIT</a> 开源 · 文档、协议与 Schema 基于 <a href="LICENSE-DOCS-CC-BY-4.0">CC BY 4.0</a> 许可 · 第三方署名见 <a href="NOTICE.md">NOTICE.md</a></sub>

</div>
