# -*- coding: utf-8 -*-
"""Skill 注册表：把 skills/*/prompt.md 加载成后端可直接使用的 system prompt。

设计原则：不改动任何 prompt 原文，只在调用时追加一段"输出格式适配"说明，
保证仓库里的 prompt.md 仍然是码道平台上的那一份（证据链可追溯）。
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

# 四个并行评审 Skill（顺序即前端展示顺序）
REVIEW_SKILLS = [
    {
        "key": "security",
        "name": "安全评审",
        "short": "安全",
        "prompt_file": "security-review/prompt.md",
    },
    {
        "key": "performance",
        "name": "性能评审",
        "short": "性能",
        "prompt_file": "performance-review/prompt.md",
    },
    {
        "key": "architecture",
        "name": "架构评审",
        "short": "架构",
        "prompt_file": "architecture-review/prompt.md",
    },
    {
        "key": "standard",
        "name": "规范评审",
        "short": "规范",
        "prompt_file": "standard-review/prompt.md",
    },
]

CONFLICT_SKILL = {
    "key": "conflict",
    "name": "冲突汇总",
    "short": "汇总",
    "prompt_file": "conflict-summary/prompt.md",
}

# 输出格式适配层：让模型先给一个可解析的等级行，再给分析正文。
# 这样前端能立刻更新指标卡，同时正文保持人类可读。
LEVEL_HINT = """

---
【输出格式（必须遵守）】
第一行只输出：LEVEL: <低|中|高>
第二行起输出分析正文：纯文本，不要 Markdown 标题符号（#、##），不要代码块围栏，
条目之间空一行，总长度不超过 300 字。
"""


def _read(rel: str) -> str:
    p = SKILLS_DIR / rel
    if not p.exists():
        raise FileNotFoundError(f"找不到 Skill prompt：{p}")
    return p.read_text(encoding="utf-8")


def system_prompt(skill: dict) -> str:
    """评审类 Skill：prompt.md 原文 + 输出格式适配。"""
    return _read(skill["prompt_file"]) + LEVEL_HINT


def conflict_prompt() -> str:
    """汇总 Skill：直接用 conflict-summary 原文。"""
    return _read(CONFLICT_SKILL["prompt_file"])


def all_skill_meta() -> list:
    return [
        {"key": s["key"], "name": s["name"], "short": s["short"]}
        for s in REVIEW_SKILLS
    ]
