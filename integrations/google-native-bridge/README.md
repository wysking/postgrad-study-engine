# Google-Native Bridge for Gemini (Drive / Gmail + Apps Script V8 → GitHub Actions)

[简体中文说明](#5-分钟部署指南) · [English Quick Setup](#5-minute-setup-guide) · [Dual AI Integration Guide](../../docs/AI_INTEGRATIONS.md)

一套**零付费大模型 API、零第三方远程 GitHub MCP、零 GCP 绑卡、零 7 天过期测试态 OAuth、零 Service Account、零公网 Web App `doPost` 暴露**的个人云端桥接模板。  
让 Google AI Pro 原生 **Gemini 聊天与定时任务** 通过第一方 **Google Drive / Gmail** 连接器无缝读写你的私有 GitHub Vault。

## 目录内容

| 文件 | 用途 |
| :--- | :--- |
| [Code.gs](Code.gs) | 单文件 Google Apps Script V8 网桥（含 Drive v3 原地快写、SHA 跳过、4 条上行通道、Core v0.5.1 本地校验、GET-before-PUT 幂等/冲突保护、`LockService`） |
| [appsscript.json](appsscript.json) | Apps Script 清单（声明启用 `Drive` v3 高级服务、V8、最小 OAuth 权限，无 `webapp`） |
| [GEMINI_TUTOR_SKILL.md](GEMINI_TUTOR_SKILL.md) | 零 GitHub MCP 的日常辅导 Gemini Skill / Gem 系统指令模板 |
| [GEMINI_DAILY_REVIEW_PROMPT.md](GEMINI_DAILY_REVIEW_PROMPT.md) | 每日 02:00 定时定性复盘 Gemini Scheduled Actions 提示词模板 |
| [tests/bridge.test.mjs](tests/bridge.test.mjs) | 零依赖 Node.js 单元测试（`node --test integrations/google-native-bridge/tests/bridge.test.mjs`） |

---

## 5 分钟部署指南

### 1. 签发单仓 GitHub Fine-Grained PAT
在 GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**：
- **Repository access**：仅选择你自己的私有 Vault 仓库（`<YOUR_GITHUB_USERNAME>/<YOUR_PRIVATE_VAULT_REPO>`）
- **Repository permissions**：只开 **`Contents: Read and write`**（GitHub 自动附带 `Metadata: Read-only`），其余全部 `No access`。

### 2. 创建 Google Apps Script 项目
1. 打开 <https://script.google.com> → 新建项目，命名为 `Postgrad-Bridge`。
2. 打开左侧 **项目设置（Project Settings）**：
   - 勾选 **在编辑器中显示“appsscript.json”清单文件**。
   - 在 **脚本属性（Script Properties）** 中新增以下 3 项并保存：
     - `GITHUB_TOKEN` = 第 1 步生成的 `github_pat_...`
     - `GITHUB_OWNER` = 你的 GitHub 用户名
     - `GITHUB_REPO` = 你的私有 Vault 仓库名
3. 切回 **编辑器（`<>`）**：
   - 将 [appsscript.json](appsscript.json) 完整粘贴覆盖 `appsscript.json` 并保存（左侧「服务」会自动启用 **`Drive` v3**，确保几百 KB 大文档 2–3 秒原地覆写不超时）。
   - 将 [Code.gs](Code.gs) 完整粘贴覆盖 `代码.gs` 并保存。

### 3. 一键初始化 Drive 镜像与 5 分钟触发器
1. 顶部函数下拉框选 **`setupBridge`** → 点 **运行** → 首次按提示给自己的私人脚本点一次授权允许。
2. 运行完成后自动完成：
   - 在 Google Drive 根目录建好 `Postgrad-Cloud/` 及 4 份只读镜像 Docs（`Postgrad-1`..`Postgrad-4`，后续更新永远保留 File ID）+ 备用队列与收件箱子目录；
   - 自动灌入当前私有 Vault 的最新内容；
   - 自动安装 **每 5 分钟** 运行一次的 `runBridgeCycle` 时间触发器。
3. **安全提示**：切勿点击「部署 → Web 应用」，本脚本不含任何 `doPost` / `doGet`。

### 4. 配置 Gemini Skill 与 02:00 定时复盘
- 在 Gemini 设置中开启 **Google Workspace（Google Drive + Gmail）** 原生扩展。
- 用 [GEMINI_TUTOR_SKILL.md](GEMINI_TUTOR_SKILL.md) 配置日常辅导 Skill / Gem。
- 在 Gemini **定时操作（Scheduled actions）** 中新建每日 02:00 任务，粘贴 [GEMINI_DAILY_REVIEW_PROMPT.md](GEMINI_DAILY_REVIEW_PROMPT.md)。

### 5. 本地验证脚本测试（可选）

```sh
node --test integrations/google-native-bridge/tests/bridge.test.mjs
```

---

## 5-Minute Setup Guide

1. **Create a single-repo GitHub Fine-Grained PAT** scoped ONLY to your private Vault repository with `Contents: Read and write` (`Metadata: Read-only`).
2. **Create a personal Google Apps Script project** at <https://script.google.com>, show `appsscript.json` in Project Settings, and set `ScriptProperties`:
   - `GITHUB_TOKEN`: your PAT
   - `GITHUB_OWNER`: your GitHub username
   - `GITHUB_REPO`: your private Vault repository name
3. **Paste [`appsscript.json`](appsscript.json)** (enables Drive API v3 for fast in-place updates without DocumentApp timeouts) **and [`Code.gs`](Code.gs)**, then run **`setupBridge()`** once to bootstrap `Postgrad-Cloud/` in Google Drive and install the 5-minute `runBridgeCycle` trigger (do **not** deploy a Web App).
4. **Configure Gemini** with Google Workspace (Drive + Gmail) enabled using [`GEMINI_TUTOR_SKILL.md`](GEMINI_TUTOR_SKILL.md) and [`GEMINI_DAILY_REVIEW_PROMPT.md`](GEMINI_DAILY_REVIEW_PROMPT.md).
