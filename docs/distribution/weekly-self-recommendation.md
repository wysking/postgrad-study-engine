# 【开源自荐】Postgrad Study Engine：考研 AI 私教学习引擎，让学习档案、遗忘曲线与错因核查可重放

状态：投稿草稿，尚未向站外发送。目标：`ruanyf/weekly` Issue。

我是 Postgrad Study Engine 的维护者，本次为项目自荐。

项目地址：https://github.com/wysking/postgrad-study-engine

当前版本：https://github.com/wysking/postgrad-study-engine/releases/tag/v0.5.0

它面向考研和长期自学，提供一个可独立部署的 Python 学习引擎：教学前台负责解释与追问，
每位学习者的私人 Vault 保存真实作答、提示条件、错因修订和复习依据。
看懂解释、提示后完成、独立求解与延迟保持分别记录，缺失事实保持未知。

v0.5.0 已实现：

- 空白档案初始化、课程注册、匹配回执归档、今日简报和本地 HTML 仪表盘；
- 对合格原子回忆进行正则化半衰期拟合与时间顺序评估；可选 FSRS 使用明确观察到的难易评分；
- 基于课程先修关系、已观察失败和证据缺口，建议少量待验证探针；
- 离线参考教学、可选 OpenAI Responses 适配和仓库教学 Skill。

可以直接跑一个九单元、14 天的虚构重放：

```sh
git clone --branch v0.5.0 https://github.com/wysking/postgrad-study-engine.git
cd postgrad-study-engine
python -m scripts.study demo --vault ../fictional-study-demo
```

打开演示目录的 `reports/demo.html`，可以看到独立成功、第三天失败、辅助纠正和后续检查的区别。
入门：https://github.com/wysking/postgrad-study-engine/blob/main/docs/GETTING_STARTED.md

本项目公开了软件测试及合成校准检查，但没有证明真实人群的预测校准、提分或节时效果。
模型输出先作为教学参考，正式排程仍使用原规则。它没有托管账号系统、完整题库或专用 Obsidian 插件。
Python 代码采用 MIT；文档、协议、Schema 与模板采用 CC BY 4.0，第三方教材与题库不包含在内。

欢迎对数据资格、教学闭环、课程扩展和模型评估提出建议。
