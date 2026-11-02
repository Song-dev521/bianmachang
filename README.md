\# 辩码场｜多Skill冲突消解的软件工程权衡教学智能体

> 2026 华为开发者大赛 · 智能体创新赛（西南赛区）· 高校组



\## 项目简介

本项目基于华为云码道CodeArts智能体平台构建，核心目标\*\*不是自动给代码打分、不是自动修复代码\*\*，而是模拟多名不同侧重点的软件评审专家，独立对同一段代码产出评审意见，并且把评审意见之间天然存在的工程权衡冲突暴露出来，用作软件工程课程的教学案例，让学习者看懂：软件工程里很多问题没有唯一标准答案，只有取舍。



项目由5个独立Skill + 1个主调度智能体组成：

1\. `security-review`：代码安全视角评审

2\. `performance-review`：性能开销视角评审

3\. `architecture-review`：架构分层与可扩展性评审

4\. `standard-review`：编码规范、可读性评审

5\. `conflict-summary`：冲突汇总分析Skill，提取共识、识别权衡冲突、输出多套可选方案



主智能体 `bianmachang-main` 接收用户输入代码，依次调用4个评审Skill收集四份独立报告，交由冲突汇总Skill结构化输出冲突结果。



\## 测试样例

```python

import sqlite3

username = input("请输入用户名：")

conn = sqlite3.connect("test.db")

cursor = conn.cursor()

sql = f"select \* from user where name='{username}'"

cursor.execute(sql)



