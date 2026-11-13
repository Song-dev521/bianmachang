# -*- coding: utf-8 -*-
"""模型调用层：两条 provider，可自动降级。

- MaasProvider   ：华为云 ModelArts Studio（MaaS）OpenAI 兼容接口，真实调用
- ReplayProvider ：回放 codearts_proof/run_log 里的真实运行输出，无网无 Key 也能演示

选择逻辑（MODE 环境变量）：
  auto   —— 有 MAAS_API_KEY 走真实调用，没有则回放（默认）
  maas   —— 强制真实调用，缺 Key 直接报错
  replay —— 强制回放
"""
import asyncio
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPLAY_FILE = HERE / "replay.json"

DEFAULT_BASE_URL = "https://api.modelarts-maas.com/openai/v1"
DEFAULT_MODEL = "deepseek-v4.1-flash-1017"

# 模型白名单：硬约束。只允许调用下面列出的模型，防止误配置消耗其他模型额度。
ALLOWED_MODELS = {"deepseek-v4.1-flash-1017"}

_LEVEL_RE = re.compile(r"^\s*(?:LEVEL|等级|评级)\s*[:：]\s*[\*\s]*(低|中|高)", re.I | re.M)

# 等级关键词：不同 Skill 的措辞不一样，用加权投票比只认一行更稳
_HIGH_KW = ("高危", "严重", "致命", "Critical", "不可接受", "必须立即", "存在注入", "越权")
_MID_KW = ("有缺陷", "较多问题", "一般", "中等", "待改进", "需要修复", "建议修复", "职责不单一")
_LOW_KW = ("良好", "优秀", "无问题", "低风险", "可接受", "结构清晰")


def parse_level(text: str) -> str:
    """综合判定等级：显式 LEVEL 行加权 + 内容关键词投票，取得分最高一档（同分偏严重）。"""
    t = text or ""
    explicit = None
    m = _LEVEL_RE.search(t)
    if m:
        explicit = {"低": "low", "中": "mid", "高": "high"}[m.group(1)]

    score = {
        "high": sum(t.count(k) for k in _HIGH_KW) * 2,
        "mid": sum(t.count(k) for k in _MID_KW) * 2,
        "low": sum(t.count(k) for k in _LOW_KW) * 2,
    }
    if explicit:
        score[explicit] += 3

    best = max(score, key=lambda k: (score[k], {"high": 3, "mid": 2, "low": 1}[k]))
    if best == "low":
        # 正文里只要列出了具体问题位置（"位置："），就说明存在实质问题，不得评为低
        issues = t.count("位置：") + t.count("位置:")
        if issues >= 1:
            return "mid"
    return best if score[best] > 0 else "mid"


def strip_level(text: str) -> str:
    """去掉 LEVEL 行，只留正文。"""
    lines = [ln for ln in (text or "").splitlines()]
    out = []
    skipped = False
    for ln in lines:
        if not skipped and _LEVEL_RE.match(ln):
            skipped = True
            continue
        out.append(ln)
    return "\n".join(out).strip()


class MaasProvider:
    """华为云 MaaS，OpenAI 兼容协议。"""

    mode = "maas"

    def __init__(self):
        from openai import AsyncOpenAI  # 延迟导入，回放模式不需要装

        api_key = os.getenv("MAAS_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("未配置 MAAS_API_KEY")
        self.model = os.getenv("MAAS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        if self.model not in ALLOWED_MODELS:
            raise RuntimeError(
                f"模型 {self.model!r} 不在允许列表内，仅允许：{', '.join(sorted(ALLOWED_MODELS))}"
            )
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=os.getenv("MAAS_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
        )
        self.timeout = float(os.getenv("REVIEW_TIMEOUT", "60"))
        # 该模型带思考过程，输出预算要给足，否则正文会被 reasoning 吃空
        self.max_tokens = int(os.getenv("MAX_TOKENS", "2048"))

    async def complete(self, system: str, user: str) -> str:
        resp = await asyncio.wait_for(
            self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=self.max_tokens,
            ),
            timeout=self.timeout,
        )
        msg = resp.choices[0].message
        text = (msg.content or "").strip()
        if not text:
            # 极端情况下正文为空，退回思考内容，避免前端拿到空白卡片
            text = (getattr(msg, "reasoning_content", "") or "").strip()
        return text


class ReplayProvider:
    """回放真实运行记录（内容来自 codearts_proof/run_log）。"""

    mode = "replay"

    def __init__(self):
        self.data = json.loads(REPLAY_FILE.read_text(encoding="utf-8"))
        self.model = "replay（真实运行记录回放）"

    async def complete(self, system: str, user: str) -> str:
        # 按 system prompt 的首行特征判断是哪个 Skill
        key = self._match(system)
        item = self.data["skills"].get(key) or self.data["conflict"]
        await asyncio.sleep(item.get("delay", 1.0))
        return item["text"]

    def _match(self, system: str) -> str:
        for key, item in self.data["skills"].items():
            if item.get("marker") and item["marker"] in system:
                return key
        return "conflict"


def build_provider():
    """按 MODE 决定用哪个 provider，返回 (provider, 提示信息)。"""
    mode = os.getenv("MODE", "auto").strip().lower()
    has_key = bool(os.getenv("MAAS_API_KEY", "").strip())

    if mode == "replay":
        return ReplayProvider(), "强制回放模式"
    if mode == "maas":
        return MaasProvider(), "强制真实调用"
    # auto
    if has_key:
        try:
            return MaasProvider(), "已连接华为云 MaaS"
        except Exception as exc:  # 依赖没装等
            return ReplayProvider(), f"MaaS 初始化失败，降级回放：{exc}"
    return ReplayProvider(), "未配置 MAAS_API_KEY，使用真实运行记录回放"
