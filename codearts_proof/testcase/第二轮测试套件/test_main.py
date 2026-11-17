# -*- coding: utf-8 -*-
"""main 模块测试：健康检查、首页、SSE 帧格式、/api/review 事件流水线。

核心约束（对应本轮需求）：
- **不走真实 socket**：review 的 SSE generator 是路由函数内部的闭包，无法直接引用，
  因此通过 ``await main.review(FakeRequest(...))`` 拿到 ``StreamingResponse`` 后，
  直接异步迭代 ``response.body_iterator`` 取事件帧 —— 全程不经过 HTTP / ASGI / socket。
- **不调外部模型**：``main.build_provider`` 与 ``provider.complete()`` 全部替换为假实现
  （``unittest.mock.patch``，与 pytest ``monkeypatch`` 同一替换机制）。
- **只断言事件顺序与数据结构**：每个 SSE 帧单独解析，断言 event 名、JSON 可解析、字段集合与取值。
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import _asyncio_compat  # noqa: E402,F401  （选择 socket-free 事件循环）

import main
import prompts

ENV_KEYS = (
    "MODE",
    "MAAS_API_KEY",
    "MAAS_MODEL",
    "MAAS_BASE_URL",
    "REVIEW_TIMEOUT",
    "MAX_TOKENS",
)

REVIEW_CODE = "def handler(user_input):\n    return eval(user_input)"
FAKE_NOTE = "假 provider（测试）"
REVIEW_TEXT = "LEVEL: 高\n存在注入风险，必须立即修复"
SUMMARY_TEXT = "LEVEL: 中\n汇总结论：安全与性能需要权衡"

SKILL_PROMPT_BODY = "# {name}\n你是{name}专家，请给出评审意见。"
CONFLICT_PROMPT_BODY = "# 冲突汇总\n请在以下评审中找出冲突并给出结论。"


class EnvIsolatedTestCase(unittest.TestCase):
    """清空会触发真实模型的真实环境变量，用例结束后原样恢复。"""

    def setUp(self):
        self._env_backup = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class FakeRequest:
    """最小 Request 替身：只实现 review 用到的 ``json()``。"""

    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class FakeProvider:
    """假 provider：``complete()`` 不发起任何外部调用，只记录入参并返回固定文本。"""

    mode = "replay"
    model = "fake-model"

    def __init__(
        self,
        review_text=REVIEW_TEXT,
        summary_text=SUMMARY_TEXT,
        skill_error=None,
        conflict_error=None,
    ):
        self.review_text = review_text
        self.summary_text = summary_text
        self.skill_error = skill_error
        self.conflict_error = conflict_error
        self.calls = []

    async def complete(self, system, user):
        self.calls.append({"system": system, "user": user})
        await asyncio.sleep(0)  # 让四个评审任务真正并发交错
        if prompts.CONFLICT_SKILL["name"] in system:  # 汇总 prompt 含“冲突汇总”
            if self.conflict_error is not None:
                raise self.conflict_error
            return self.summary_text
        if self.skill_error is not None:
            raise self.skill_error
        return self.review_text


async def _drain(response):
    """直接异步迭代 SSE 生成器，不触发 HTTP 层。"""
    chunks = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, (bytes, bytearray)):
            chunk = chunk.decode("utf-8")
        chunks.append(chunk)
    return chunks


def parse_sse_frames(chunks):
    """把帧文本解析成 [{event, payload, block}]，同时保留原始块用于格式断言。"""
    text = "".join(chunks)
    blocks = [block for block in text.split("\n\n") if block.strip()]
    frames = []
    for block in blocks:
        lines = block.splitlines()
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        frames.append({"event": event, "payload": json.loads(data), "block": block})
    return text, frames


def _write_prompt_tree(root, with_conflict=True):
    for skill in prompts.REVIEW_SKILLS:
        path = root / skill["prompt_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SKILL_PROMPT_BODY.format(name=skill["name"]), encoding="utf-8")
    if with_conflict:
        path = root / prompts.CONFLICT_SKILL["prompt_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CONFLICT_PROMPT_BODY, encoding="utf-8")


class FakeProviderTestBase(EnvIsolatedTestCase):
    """统一装配：临时 Skill prompt 目录 + 假 provider + 假 build_provider。"""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.skills_dir = Path(tmp.name)
        _write_prompt_tree(self.skills_dir)

        patcher = mock.patch.object(prompts, "SKILLS_DIR", self.skills_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.provider = FakeProvider()
        provider_patcher = mock.patch.object(
            main, "build_provider", lambda: (self.provider, FAKE_NOTE)
        )
        provider_patcher.start()
        self.addCleanup(provider_patcher.stop)

    def collect_review(self, payload=None):
        request = FakeRequest(payload if payload is not None else {"code": REVIEW_CODE})
        response = asyncio.run(main.review(request))
        if not hasattr(response, "body_iterator"):  # 参数校验失败：JSONResponse
            return response, []
        return response, asyncio.run(_drain(response))


# --------------------------------------------------------------------------- #
# 1. 健康检查
# --------------------------------------------------------------------------- #
class HealthTest(FakeProviderTestBase):
    def test_health_direct_call_exposes_mode_and_model(self):
        """直调路由函数：不依赖 socket，也能验证返回体字段。"""
        body = asyncio.run(main.health())

        self.assertEqual(set(body), {"status", "mode", "model", "note", "skills"})
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["mode"], "replay")
        self.assertEqual(body["model"], "fake-model")
        self.assertEqual(body["note"], FAKE_NOTE)
        self.assertEqual(
            [skill["key"] for skill in body["skills"]],
            ["security", "performance", "architecture", "standard"],
        )
        self.assertEqual(
            [skill["name"] for skill in body["skills"]],
            ["安全评审", "性能评审", "架构评审", "规范评审"],
        )
        for meta in body["skills"]:
            self.assertEqual(set(meta), {"key", "name", "short"})

    def test_health_endpoint_over_http_if_available(self):
        """HTTP 写法：沙箱若拦截 socket/ASGI 传输则跳过，不影响其余用例。"""
        try:
            from fastapi.testclient import TestClient

            response = TestClient(main.app).get("/api/health")
        except Exception as exc:  # noqa: BLE001 - 沙箱可拦截 socket/依赖
            self.skipTest(f"沙箱拦截 socket/ASGI 传输：{exc}")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], "replay")
        self.assertEqual(body["model"], "fake-model")
        self.assertEqual(len(body["skills"]), 4)


# --------------------------------------------------------------------------- #
# 首页与 SSE 帧格式
# --------------------------------------------------------------------------- #
class IndexAndFrameTest(FakeProviderTestBase):
    def test_index_returns_404_when_html_missing(self):
        missing = self.skills_dir / "not-exists.html"
        with mock.patch.object(main, "INDEX_HTML", missing):
            response = asyncio.run(main.index())

        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.body), {"error": "index.html 不存在"})

    def test_index_serves_html_when_file_exists(self):
        html = self.skills_dir / "index.html"
        html.write_text("<html><body>辩码场</body></html>", encoding="utf-8")
        with mock.patch.object(main, "INDEX_HTML", html):
            response = asyncio.run(main.index())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "text/html")
        self.assertEqual(Path(response.path), html)

    def test_sse_frame_keeps_chinese_readable(self):
        frame = main.sse("skill", {"key": "安全", "n": 1})

        self.assertEqual(frame, 'event: skill\ndata: {"key": "安全", "n": 1}\n\n')


# --------------------------------------------------------------------------- #
# 4. /api/review 的 SSE 事件顺序与数据结构
# --------------------------------------------------------------------------- #
class ReviewStreamTest(FakeProviderTestBase):
    def test_review_stream_event_order(self):
        response, chunks = self.collect_review()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(
            dict(response.headers)["cache-control"], "no-cache"
        )
        self.assertEqual(dict(response.headers)["x-accel-buffering"], "no")

        text, frames = parse_sse_frames(chunks)
        events = [frame["event"] for frame in frames]

        # 实现层顺序（含开始汇总的进度事件）
        self.assertEqual(
            events,
            ["start", "skill", "skill", "skill", "skill", "conflict_start", "conflict", "done"],
        )
        # 需求层业务顺序：start → skill×4 → conflict → done
        self.assertEqual(
            [event for event in events if event != "conflict_start"],
            ["start", "skill", "skill", "skill", "skill", "conflict", "done"],
        )
        self.assertLess(events.index("start"), events.index("skill"))
        self.assertGreater(events.index("done"), events.index("conflict"))
        self.assertTrue(text.endswith("\n\n"))

    def test_review_every_frame_is_well_formed(self):
        _, chunks = self.collect_review()
        _, frames = parse_sse_frames(chunks)

        self.assertEqual(len(frames), 8)
        for frame in frames:
            lines = frame["block"].splitlines()
            self.assertEqual(len(lines), 2, f"帧应为 event+data 两行：{frame['block']!r}")
            self.assertTrue(lines[0].startswith("event: "))
            self.assertTrue(lines[1].startswith("data: "))
            self.assertIsInstance(frame["payload"], dict)

    def test_start_payload_carries_mode_model_and_skill_meta(self):
        _, chunks = self.collect_review()
        _, frames = parse_sse_frames(chunks)

        start = frames[0]
        self.assertEqual(start["event"], "start")
        payload = start["payload"]
        self.assertEqual(set(payload), {"mode", "model", "note", "skills"})
        self.assertEqual(payload["mode"], "replay")
        self.assertEqual(payload["model"], "fake-model")
        self.assertEqual(payload["note"], FAKE_NOTE)
        self.assertEqual(
            [(meta["key"], meta["name"], meta["short"]) for meta in payload["skills"]],
            [(skill["key"], skill["name"], skill["short"]) for skill in prompts.REVIEW_SKILLS],
        )

    def test_four_skill_payloads_have_complete_structure(self):
        _, chunks = self.collect_review()
        _, frames = parse_sse_frames(chunks)

        skill_payloads = [frame["payload"] for frame in frames if frame["event"] == "skill"]
        self.assertEqual(len(skill_payloads), 4)
        self.assertEqual(
            {payload["key"] for payload in skill_payloads},
            {skill["key"] for skill in prompts.REVIEW_SKILLS},
        )
        self.assertEqual(
            {payload["name"] for payload in skill_payloads},
            {skill["name"] for skill in prompts.REVIEW_SKILLS},
        )
        expected_names = {skill["name"]: skill["short"] for skill in prompts.REVIEW_SKILLS}
        for payload in skill_payloads:
            self.assertEqual(set(payload), {"key", "name", "short", "level", "text", "ms"})
            self.assertEqual(payload["short"], expected_names[payload["name"]])
            self.assertEqual(payload["level"], "high")
            self.assertEqual(payload["text"], "存在注入风险，必须立即修复")
            self.assertNotIn("LEVEL:", payload["text"])
            self.assertIsInstance(payload["ms"], int)
            self.assertGreaterEqual(payload["ms"], 0)

    def test_conflict_and_done_payloads_match_business_contract(self):
        _, chunks = self.collect_review()
        _, frames = parse_sse_frames(chunks)
        by_event = {}
        for frame in frames:
            by_event.setdefault(frame["event"], []).append(frame["payload"])

        self.assertEqual(by_event["conflict_start"], [{"name": prompts.CONFLICT_SKILL["name"]}])

        conflict = by_event["conflict"][0]
        self.assertEqual(set(conflict), {"name", "text", "ms"})
        self.assertEqual(conflict["name"], prompts.CONFLICT_SKILL["name"])
        self.assertEqual(conflict["text"], "汇总结论：安全与性能需要权衡")
        self.assertIsInstance(conflict["ms"], int)

        done = by_event["done"][0]
        self.assertEqual(set(done), {"total_ms", "mode", "complete"})
        self.assertIs(done["complete"], True)
        self.assertEqual(done["mode"], "replay")
        self.assertIsInstance(done["total_ms"], int)
        self.assertGreaterEqual(done["total_ms"], 0)

    def test_provider_receives_skill_prompts_then_conflict_context(self):
        self.collect_review()

        calls = self.provider.calls
        self.assertEqual(len(calls), 5)
        self.assertEqual([call["user"] for call in calls[:4]], [REVIEW_CODE] * 4)
        for call in calls[:4]:
            self.assertIn("【输出格式（必须遵守）】", call["system"])
        self.assertEqual(len({call["system"] for call in calls[:4]}), 4)

        summary_call = calls[4]
        self.assertEqual(summary_call["system"], prompts.conflict_prompt())
        for skill in prompts.REVIEW_SKILLS:
            self.assertIn(f"【{skill['name']}（LEVEL=high）】", summary_call["user"])
        self.assertIn("存在注入风险，必须立即修复", summary_call["user"])
        self.assertEqual(summary_call["user"].count("【"), 4)


class ReviewRejectionTest(FakeProviderTestBase):
    def test_review_rejects_blank_code(self):
        response, _ = self.collect_review({"code": "   \n\t "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body), {"error": "code 不能为空"})
        self.assertEqual(self.provider.calls, [])

    def test_review_rejects_missing_code_field(self):
        response, _ = self.collect_review({})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body), {"error": "code 不能为空"})
        self.assertEqual(self.provider.calls, [])


class ReviewFailurePathTest(FakeProviderTestBase):
    def test_skill_errors_skip_conflict_summary(self):
        self.provider.skill_error = RuntimeError("模型调用超时")

        _, chunks = self.collect_review()
        _, frames = parse_sse_frames(chunks)
        events = [frame["event"] for frame in frames]

        self.assertEqual(
            events, ["start", "skill_error", "skill_error", "skill_error", "skill_error", "error", "done"]
        )

        skill_errors = [f["payload"] for f in frames if f["event"] == "skill_error"]
        for payload in skill_errors:
            self.assertEqual(set(payload), {"key", "name", "short", "error"})
            self.assertEqual(payload["error"], "RuntimeError: 模型调用超时")
        self.assertEqual(
            {payload["key"] for payload in skill_errors},
            {skill["key"] for skill in prompts.REVIEW_SKILLS},
        )

        error = frames[-2]["payload"]
        self.assertEqual(set(error), {"message", "succeeded"})
        self.assertEqual(error["message"], "存在评审失败，已跳过冲突汇总")
        self.assertEqual(error["succeeded"], [])
        self.assertIs(frames[-1]["payload"]["complete"], False)
        self.assertEqual(len(self.provider.calls), 4)

    def test_conflict_error_still_emits_done(self):
        self.provider.conflict_error = ValueError("汇总模型不可用")

        _, chunks = self.collect_review()
        _, frames = parse_sse_frames(chunks)
        events = [frame["event"] for frame in frames]

        self.assertEqual(
            events,
            ["start", "skill", "skill", "skill", "skill", "conflict_start", "conflict_error", "done"],
        )

        conflict_error = frames[-2]["payload"]
        self.assertEqual(set(conflict_error), {"error"})
        self.assertEqual(conflict_error["error"], "ValueError: 汇总模型不可用")
        self.assertIs(frames[-1]["payload"]["complete"], True)
        self.assertEqual(len(self.provider.calls), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)