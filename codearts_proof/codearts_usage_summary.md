# 华为云码道（CodeArts）平台深度使用总结

> 项目：辩码场——多 Skill 冲突消解的软件工程权衡教学智能体
> 本文档对应大赛评分项"码道深度使用"，说明本项目在码道平台上做了什么、怎么做的、与"简单调用一次大模型"的本质区别。

---

## 一、总览

本项目没有把码道当作"一个能聊天的大模型对话框"，而是把码道当作**多智能体工程的开发、调试、编排与验证平台**，完整走完了「Skill 设计 → Prompt 迭代 → 单 Skill 调试 → 流水线并行编排 → 端到端联调 → 多用例回归 → 证据归档」七个环节。全程在码道平台内完成，关键环节均有截图与运行记录留痕（见 `screenshot/`、`run_log/`、`testcase/`）。

## 二、平台能力使用清单

| 码道能力 | 本项目的使用方式 | 证据 |
| ---- | ---- | ---- |
| 智能体（Agent）创建 | 创建主智能体 `bianmachang` 作为流水线宿主 | `screenshot/agent_01_bianmachang_create.png` |
| Skill 技能封装 | 将 4 个评审视角 + 1 个冲突汇总分别封装为 5 个独立 Skill，单一职责、互不越界 | `screenshot/skill_0*_0*_*.png`（每个 Skill 的创建信息、平台内 Prompt 配置页） |
| Prompt 在线调试 | 每个 Skill 在平台内逐版调试：v1 简单版 → final 结构化版，迭代理由见 `skill_prompt/` | `screenshot/skill_*_version_compare.png` |
| 智能体 IDE | 在码道 IDE 内编写测试用例代码、直接调用智能体对话验证 | `testcase/case_*.py.png`（IDE 内编辑 + 运行同屏） |
| 流水线编排 | 将 4 个评审 Skill 配置为**并行分支**，输出汇聚到冲突汇总 Skill | `screenshot/agent_02_full_pipeline_demo*.png`（4 张编排视图） |
| 流水线运行与日志 | 端到端联调并留存完整运行输出 | `run_log/pipeline_run_test.md` |
| 代码版本管理 | 平台内代码仓（Gitee）托管，Skill 归档分 commit 提交 | `screenshot/gitee_new_repo_create.png`、`screenshot/skill_*_05_git_push.png` |

## 三、Prompt 工程化迭代（不是照抄现成 Prompt）

5 个 Skill 全部保留 v1 → final 双版本（见 `skill_prompt/`，每个 Skill 附修改理由）。以两个典型迭代为例：

1. **security-review**：v1 只有一句"检查安全隐患"，输出格式随模型心情变化，无法与汇总 Skill 对接。final 版锁定"只评安全"的单一职责，枚举评估维度（注入、敏感信息泄露、权限控制等），并强制固定输出结构（【安全评审结论】风险等级 + 【风险点清单】位置/问题/危害/修改建议），使四份报告可被机器化汇聚。
2. **conflict-summary（核心）**：v1 把"冲突"理解成了 git 合并冲突（偏离题意）；final 版重新定义为"识别四份评审报告之间的观点矛盾"，并写入关键规则——*不单方面判定谁对谁错，只把权衡利弊交给使用者判断*，同时强制输出【多方共识项】与【权衡冲突项】分区。这一条 Prompt 规则是"本项目不输出标准答案、只暴露工程权衡"这一教学理念在工程上的直接落地。

## 四、与"简单调用大模型"的区别

1. **角色隔离而非单 Prompt 全包**：单 Prompt 让一个模型同时做四维评审，模型会倾向自我调和、把真实分歧抹平；本项目用 4 个互相隔离的 Skill 并行输出，保证分歧是"真实的"（详细论证见 `design_think.md`）。
2. **并行流水线编排**：4 个评审分支并行执行、互不等待，一次输入即可在约 40 秒内得到四个维度的完整结构化报告，再统一进入冲突汇总——这是平台编排能力，不是单轮对话。
3. **结构化输出契约**：每个 Skill 的输出格式被 Prompt 固定，使汇总 Skill 可以按区块对齐比对，冲突识别因此可工程化复现。
4. **完整验证闭环**：3 类共 4 份测试用例 + 5 份单 Skill 测试 + 1 次流水线联调，全部在平台内完成并归档（见 `test_report.md`）。

## 五、资源与产物归档

- Skill Prompt 双版本 + 修改理由：`skill_prompt/`（10 份 Prompt + 5 份说明）
- 平台操作与运行截图：`screenshot/`（134 张）
- 运行输出记录：`run_log/`（8 份 md）
- 测试代码与用例运行截图：`testcase/`
- 测试报告：`test_report.md`
- 架构选型思考：`design_think.md`
