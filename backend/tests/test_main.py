# -*- coding: utf-8 -*-
"""main 模块 API 单元测试：健康检查、首页、SSE 评审流水线。

所有用例都把 provider 的 ``complete()`` 换成假实现（monkeypatch），
并通过 autouse fixture 清空 MAAS_API_KEY，保证不会真实调用外部模型接口。
"""
import asyncio
import json
import re

import pytest
from fastapi.testclient import TestClient

import main
import prompts
import providers

client = TestClient(main.app)

REVIEW_CODE = "def handler(user_input):\n    return eval(user_input)"


def _events(text: str):
    """按出现顺序返回 SSE 事件名。"""
    return [m.group(1) for m in re.finditer(r"^event: (\w+)$", text, re.M)]


def _payloads(text: str):
    """把 SSE 文本解析成 {事件名: [payload, ...]}。"""
    parsed = {}
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(ln[len("event: "):] for ln in lines if ln.startswith("event: "))
        data = next(ln[len("data: "):] for ln in lines if ln.startswith("data: "))
        parsed.setdefault(event, []).append(json.loads(data))
    return parsed


# --------------------------------------------------------------------------- #
# 1. 健康检查
# --------------------------------------------------------------------------- #
def test_health_returns_200_with_mode_and_model():
    resp = client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "replay"
    assert body["model"]
    assert set(body) >= {"status", "mode", "model", "note", "skills"}


def test_health_lists_all_four_review_skills():
    body = client.get("/api/health").json()

    assert [s["key"] for s in body["skills"]] == [
        "security",
        "performance",
        "architecture",
        "standard",
    ]
    assert [s["name"] for s in body["skills"]] == [
        "安全评审",
        "性能评审",
        "架构评审",
        "规范评审",
    ]


# --------------------------------------------------------------------------- #
# 首页
# --------------------------------------------------------------------------- #
def test_index_serves_html():
    resp = client.get("/")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "辩码场" in resp.text


def test_index_returns_404_when_html_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "INDEX_HTML", tmp_path / "not-exists.html")

    resp = client.get("/")

    assert resp.status_code == 404
    assert resp.json() == {"error": "index.html 不存在"}


# --------------------------------------------------------------------------- #
# 4. /api/review 的 SSE 事件顺序
# --------------------------------------------------------------------------- #
def test_review_stream_order_is_start_skills_conflict_done(monkeypatch):
    monkeypatch.setenv("MODE", "replay")
    calls = []

    async def fake_complete(self, system, user):
        calls.append({"system": system, "user": user})
        await asyncio.sleep(0)  # 让四个 skill 真正并发交错
        if len(calls) > len(prompts.REVIEW_SKILLS):
            return "LEVEL: 中\n汇总结论：安全与性能需要权衡"
        return "LEVEL: 高\n存在注入风险，必须立即修复"

    monkeypatch.setattr(providers.ReplayProvider, "complete", fake_complete)

    resp = client.post("/api/review", json={"code": REVIEW_CODE})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _events(resp.text)
    # 业务顺序：start → 4 个评审 skill → 冲突汇总 → done
    # 实现上汇总前还会额外发一条 conflict_start 进度事件，一并锁定
    assert events == ["start"] + ["skill"] * 4 + ["conflict_start", "conflict", "done"]

    payloads = _payloads(resp.text)

    # start 事件带当前模式
    assert payloads["start"][0]["mode"] == "replay"

    # 四个 skill 事件各对应一个 Skill key，等级与正文来自 parse_level/strip_level
    skill_payloads = payloads["skill"]
    assert {p["key"] for p in skill_payloads} == {
        s["key"] for s in prompts.REVIEW_SKILLS
    }
    for payload in skill_payloads:
        assert payload["level"] == "high"
        assert payload["text"] == "存在注入风险，必须立即修复"
        assert payload["ms"] >= 0
    assert len({p["name"] for p in skill_payloads}) == 4

    # 冲突汇总是第 5 次调用：前 4 次拿到原始代码，汇总拿到四份评审正文拼成的上下文
    assert len(calls) == 5
    assert [c["user"] for c in calls[:4]] == [REVIEW_CODE] * 4
    conflict_context = calls[-1]["user"]
    for skill in prompts.REVIEW_SKILLS:
        assert f"【{skill['name']}（LEVEL=high）】" in conflict_context
    assert "存在注入风险，必须立即修复" in conflict_context
    assert calls[-1]["system"] == prompts.conflict_prompt()
    assert all("【输出格式（必须遵守）】" in c["system"] for c in calls[:4])

    conflict = payloads["conflict"][0]
    assert conflict["name"] == prompts.CONFLICT_SKILL["name"]
    assert conflict["text"] == "汇总结论：安全与性能需要权衡"
    assert conflict["ms"] >= 0

    done = payloads["done"][0]
    assert done["complete"] is True
    assert done["mode"] == "replay"
    assert done["total_ms"] >= 0


def test_review_rejects_empty_code():
    resp = client.post("/api/review", json={"code": "   \n\t "})

    assert resp.status_code == 400
    assert resp.json() == {"error": "code 不能为空"}


def test_review_rejects_missing_code_field():
    resp = client.post("/api/review", json={})

    assert resp.status_code == 400
    assert resp.json() == {"error": "code 不能为空"}


def test_review_skill_errors_skip_conflict_summary(monkeypatch):
    monkeypatch.setenv("MODE", "replay")

    async def failing_complete(self, system, user):
        raise RuntimeError("模型调用超时")

    monkeypatch.setattr(providers.ReplayProvider, "complete", failing_complete)

    resp = client.post("/api/review", json={"code": REVIEW_CODE})

    events = _events(resp.text)
    assert events == ["start"] + ["skill_error"] * 4 + ["error", "done"]

    payloads = _payloads(resp.text)
    for payload in payloads["skill_error"]:
        assert payload["error"] == "RuntimeError: 模型调用超时"
        assert {"key", "name", "short"} <= set(payload)
    assert payloads["error"][0]["message"] == "存在评审失败，已跳过冲突汇总"
    assert payloads["error"][0]["succeeded"] == []
    assert payloads["done"][0]["complete"] is False


def test_review_conflict_error_still_emits_done(monkeypatch):
    monkeypatch.setenv("MODE", "replay")
    calls = []

    async def complete_with_conflict_failure(self, system, user):
        calls.append(system)
        if len(calls) > len(prompts.REVIEW_SKILLS):
            raise ValueError("汇总模型不可用")
        return "LEVEL: 低\n无问题，结构清晰"

    monkeypatch.setattr(
        providers.ReplayProvider, "complete", complete_with_conflict_failure
    )

    resp = client.post("/api/review", json={"code": REVIEW_CODE})

    events = _events(resp.text)
    assert events == [
        "start",
    ] + ["skill"] * 4 + ["conflict_start", "conflict_error", "done"]

    payloads = _payloads(resp.text)
    assert payloads["conflict_start"][0]["name"] == prompts.CONFLICT_SKILL["name"]
    assert payloads["conflict_error"][0]["error"] == "ValueError: 汇总模型不可用"
    for payload in payloads["skill"]:
        assert payload["level"] == "low"
    assert payloads["done"][0]["complete"] is True


# --------------------------------------------------------------------------- #
# SSE 帧格式
# --------------------------------------------------------------------------- #
def test_sse_formats_event_frame_without_ascii_escaping():
    frame = main.sse("skill", {"key": "安全", "n": 1})

    assert frame == 'event: skill\ndata: {"key": "安全", "n": 1}\n\n'