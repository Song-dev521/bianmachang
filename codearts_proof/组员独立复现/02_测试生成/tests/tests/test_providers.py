# -*- coding: utf-8 -*-
"""providers 模块单元测试。

覆盖点：
- parse_level：显式 LEVEL 行（高/低/中）、“位置：”兜底升级、关键词加权投票、
  同分偏严重、空输入默认档
- strip_level：只剥掉首个 LEVEL 行
- MaasProvider：模型白名单硬约束、缺 Key、client 构造参数、complete 请求参数与
  空正文回退（openai 用 sys.modules 注入的假模块替代，不发起任何网络请求）
- ReplayProvider：__init__ 读取 replay 文件、marker 匹配、complete 返回
- build_provider：replay / maas / auto 三种模式与初始化失败降级
"""
import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import _asyncio_compat  # noqa: E402,F401  （选择 socket-free 事件循环）

import providers
from providers import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    MaasProvider,
    ReplayProvider,
    build_provider,
    parse_level,
    strip_level,
)

ENV_KEYS = (
    "MODE",
    "MAAS_API_KEY",
    "MAAS_MODEL",
    "MAAS_BASE_URL",
    "REVIEW_TIMEOUT",
    "MAX_TOKENS",
)

REPLAY_DATA = {
    "skills": {
        "security": {"marker": "安全评审", "text": "security 文本", "delay": 0},
        "performance": {"marker": "性能评审", "text": "performance 文本", "delay": 0},
        "architecture": {"marker": "架构评审", "text": "architecture 文本", "delay": 0},
        "standard": {"marker": "规范评审", "text": "standard 文本", "delay": 0},
    },
    "conflict": {"text": "conflict 文本", "delay": 0},
}


class EnvIsolatedTestCase(unittest.TestCase):
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


def _install_replay_file(test_case):
    """把 REPLAY_FILE 指向临时 replay.json，避免依赖仓库内真实文件。"""
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    path = Path(tmp.name) / "replay.json"
    path.write_text(json.dumps(REPLAY_DATA, ensure_ascii=False), encoding="utf-8")
    patcher = mock.patch.object(providers, "REPLAY_FILE", path)
    patcher.start()
    test_case.addCleanup(patcher.stop)
    return path


class FakeAsyncOpenAI:
    """替代 openai.AsyncOpenAI，只记录构造参数，不发请求。"""

    instances = []

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        FakeAsyncOpenAI.instances.append(self)


def _install_fake_openai(test_case, ctor=None):
    module = types.ModuleType("openai")
    module.AsyncOpenAI = ctor or FakeAsyncOpenAI
    patcher = mock.patch.dict(sys.modules, {"openai": module})
    patcher.start()
    test_case.addCleanup(patcher.stop)
    return module


# --------------------------------------------------------------------------- #
# 等级解析
# --------------------------------------------------------------------------- #
class ParseLevelTest(unittest.TestCase):
    def test_explicit_level_lines(self):
        cases = [
            ("LEVEL: 高", "high"),
            ("LEVEL: 低", "low"),
            ("LEVEL: 中", "mid"),
            ("等级：高\n补充说明", "high"),
            ("评级: 低", "low"),
            ("LEVEL: **高**", "high"),
            ("  level:高  ", "high"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_level(text), expected)

    def test_no_level_line_but_issue_position_is_mid(self):
        """需求点 2 的第三个输入：无 LEVEL 行、正文含“位置：第 12 行”。"""
        text = "整体结构尚可，未见明显风险。\n位置：第 12 行"
        self.assertEqual(parse_level(text), "mid")

    def test_explicit_low_is_upgraded_when_issue_position_present(self):
        text = "LEVEL: 低\n位置：第 12 行，存在可疑的 SQL 拼接"
        self.assertEqual(parse_level(text), "mid")

    def test_half_width_colon_position_also_upgrades(self):
        text = "LEVEL: 低\n位置: 第 8 行"
        self.assertEqual(parse_level(text), "mid")

    def test_keyword_votes(self):
        cases = [
            ("存在注入风险，且越权，属于严重问题，必须立即修复", "high"),
            ("职责不单一，建议修复，整体有缺陷", "mid"),
            ("结构清晰，无问题，低风险", "low"),
            ("这是不可接受的 Critical 缺陷", "high"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_level(text), expected)

    def test_tie_prefers_more_severe_level(self):
        self.assertEqual(parse_level("严重\n有缺陷"), "high")

    def test_empty_text_defaults_to_mid(self):
        for text in ("", None):
            with self.subTest(text=text):
                self.assertEqual(parse_level(text), "mid")

    def test_low_without_position_stays_low(self):
        self.assertEqual(parse_level("LEVEL: 低\n结构清晰，无问题"), "low")


# --------------------------------------------------------------------------- #
# LEVEL 行剥离
# --------------------------------------------------------------------------- #
class StripLevelTest(unittest.TestCase):
    def test_removes_level_line(self):
        self.assertEqual(
            strip_level("LEVEL: 高\n正文第一行\n正文第二行"), "正文第一行\n正文第二行"
        )

    def test_keeps_text_without_level_line(self):
        self.assertEqual(strip_level("  正文\n第二行  "), "正文\n第二行")

    def test_only_skips_first_matching_line(self):
        self.assertEqual(strip_level("LEVEL: 高\n正文\nLEVEL: 低"), "正文\nLEVEL: 低")

    def test_none_returns_empty_string(self):
        self.assertEqual(strip_level(None), "")


# --------------------------------------------------------------------------- #
# MaasProvider
# --------------------------------------------------------------------------- #
class MaasProviderInitTest(EnvIsolatedTestCase):
    def setUp(self):
        super().setUp()
        FakeAsyncOpenAI.instances = []
        _install_fake_openai(self)

    def test_rejects_model_outside_allowlist(self):
        """需求点 3：把 MAAS_MODEL 设为白名单外的模型名，初始化必须抛异常。"""
        os.environ["MAAS_API_KEY"] = "test-key"
        os.environ["MAAS_MODEL"] = "gpt-4o-mini"

        with self.assertRaises(RuntimeError) as ctx:
            MaasProvider()

        message = str(ctx.exception)
        self.assertIn("不在允许列表内", message)
        self.assertIn("'gpt-4o-mini'", message)
        self.assertIn(DEFAULT_MODEL, message)

    def test_rejects_blank_api_key(self):
        os.environ["MAAS_API_KEY"] = "   "
        os.environ["MAAS_MODEL"] = DEFAULT_MODEL

        with self.assertRaises(RuntimeError) as ctx:
            MaasProvider()

        self.assertEqual(str(ctx.exception), "未配置 MAAS_API_KEY")

    def test_builds_client_with_configured_values(self):
        os.environ["MAAS_API_KEY"] = "test-key"
        os.environ["MAAS_MODEL"] = DEFAULT_MODEL
        os.environ["MAAS_BASE_URL"] = "https://example.invalid/v1"
        os.environ["REVIEW_TIMEOUT"] = "12"
        os.environ["MAX_TOKENS"] = "512"

        provider = MaasProvider()

        self.assertEqual(provider.model, DEFAULT_MODEL)
        self.assertEqual(provider.timeout, 12.0)
        self.assertEqual(provider.max_tokens, 512)
        self.assertEqual(
            provider.client.init_kwargs,
            {"api_key": "test-key", "base_url": "https://example.invalid/v1"},
        )

    def test_blank_model_falls_back_to_default(self):
        os.environ["MAAS_API_KEY"] = "test-key"
        os.environ["MAAS_MODEL"] = "   "

        self.assertEqual(MaasProvider().model, DEFAULT_MODEL)

    def test_blank_base_url_falls_back_to_default(self):
        os.environ["MAAS_API_KEY"] = "test-key"
        os.environ["MAAS_BASE_URL"] = "  "

        provider = MaasProvider()

        self.assertEqual(provider.client.init_kwargs["base_url"], DEFAULT_BASE_URL)


class _FakeCompletions:
    def __init__(self, response=None, error=None, delay=0.0):
        self._response = response
        self._error = error
        self._delay = delay
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        return self._response


def _maas_with(response=None, error=None, delay=0.0):
    """绕过 __init__，直接装配带假 client 的 MaasProvider。"""
    provider = MaasProvider.__new__(MaasProvider)
    provider.model = DEFAULT_MODEL
    provider.timeout = 5.0
    provider.max_tokens = 2048
    completions = _FakeCompletions(response=response, error=error, delay=delay)
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return provider, completions


class MaasCompleteTest(unittest.TestCase):
    def test_sends_expected_request_and_strips_content(self):
        message = SimpleNamespace(content="  评审结果  ", reasoning_content="思考")
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        provider, completions = _maas_with(response=response)

        text = asyncio.run(provider.complete("系统提示", "用户代码"))

        self.assertEqual(text, "评审结果")
        self.assertEqual(
            completions.calls,
            [
                {
                    "model": DEFAULT_MODEL,
                    "messages": [
                        {"role": "system", "content": "系统提示"},
                        {"role": "user", "content": "用户代码"},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2048,
                }
            ],
        )

    def test_falls_back_to_reasoning_content_when_content_empty(self):
        message = SimpleNamespace(content="   ", reasoning_content=" 思考内容 ")
        provider, _ = _maas_with(
            response=SimpleNamespace(choices=[SimpleNamespace(message=message)])
        )

        self.assertEqual(asyncio.run(provider.complete("s", "u")), "思考内容")

    def test_returns_empty_string_when_no_content_at_all(self):
        message = SimpleNamespace(content=None, reasoning_content=None)
        provider, _ = _maas_with(
            response=SimpleNamespace(choices=[SimpleNamespace(message=message)])
        )

        self.assertEqual(asyncio.run(provider.complete("s", "u")), "")

    def test_timeout_when_client_is_slow(self):
        provider, _ = _maas_with(response=None, delay=0.05)
        provider.timeout = 0.005

        with self.assertRaises(asyncio.TimeoutError):
            asyncio.run(provider.complete("s", "u"))


# --------------------------------------------------------------------------- #
# ReplayProvider
# --------------------------------------------------------------------------- #
class ReplayProviderTest(EnvIsolatedTestCase):
    def test_init_reads_replay_file(self):
        _install_replay_file(self)

        provider = ReplayProvider()

        self.assertEqual(provider.mode, "replay")
        self.assertIn("replay", provider.model)
        self.assertEqual(
            set(provider.data["skills"]),
            {"security", "performance", "architecture", "standard"},
        )
        self.assertEqual(provider.data["conflict"]["text"], "conflict 文本")

    def _provider(self):
        provider = ReplayProvider.__new__(ReplayProvider)
        provider.model = "replay"
        provider.data = json.loads(json.dumps(REPLAY_DATA))
        return provider

    def test_match_by_marker(self):
        provider = self._provider()

        self.assertEqual(provider._match("你是安全评审专家"), "security")
        self.assertEqual(provider._match("你是性能评审专家"), "performance")
        self.assertEqual(provider._match("你是架构评审专家"), "architecture")

    def test_match_falls_back_to_conflict(self):
        provider = self._provider()

        self.assertEqual(provider._match("完全无关的 system prompt"), "conflict")

    def test_complete_returns_skill_text(self):
        provider = self._provider()

        self.assertEqual(
            asyncio.run(provider.complete("你是安全评审专家", "code")), "security 文本"
        )

    def test_complete_falls_back_to_conflict_text(self):
        provider = self._provider()

        self.assertEqual(
            asyncio.run(provider.complete("未知提示", "code")), "conflict 文本"
        )


# --------------------------------------------------------------------------- #
# build_provider
# --------------------------------------------------------------------------- #
class BuildProviderTest(EnvIsolatedTestCase):
    def test_replay_mode_forces_replay(self):
        os.environ["MODE"] = "replay"
        _install_replay_file(self)

        provider, note = build_provider()

        self.assertIsInstance(provider, ReplayProvider)
        self.assertEqual(note, "强制回放模式")

    def test_maas_mode_forces_maas(self):
        os.environ["MODE"] = "  MaAs  "
        os.environ["MAAS_API_KEY"] = "test-key"
        _install_fake_openai(self)

        provider, note = build_provider()

        self.assertIsInstance(provider, MaasProvider)
        self.assertEqual(note, "强制真实调用")

    def test_maas_mode_without_key_raises(self):
        os.environ["MODE"] = "maas"
        _install_fake_openai(self)  # __init__ 先延迟导入 openai，再校验 Key

        with self.assertRaises(RuntimeError) as ctx:
            build_provider()

        self.assertEqual(str(ctx.exception), "未配置 MAAS_API_KEY")

    def test_auto_uses_maas_when_key_present(self):
        os.environ["MAAS_API_KEY"] = "test-key"
        _install_fake_openai(self)

        provider, note = build_provider()

        self.assertIsInstance(provider, MaasProvider)
        self.assertEqual(note, "已连接华为云 MaaS")

    def test_auto_uses_replay_without_key(self):
        _install_replay_file(self)

        provider, note = build_provider()

        self.assertIsInstance(provider, ReplayProvider)
        self.assertIn("未配置 MAAS_API_KEY", note)

    def test_auto_downgrades_when_maas_init_fails(self):
        os.environ["MAAS_API_KEY"] = "test-key"
        _install_replay_file(self)

        def _broken_async_openai(**kwargs):
            raise ImportError("openai 未安装")

        _install_fake_openai(self, ctor=_broken_async_openai)

        provider, note = build_provider()

        self.assertIsInstance(provider, ReplayProvider)
        self.assertIn("降级回放", note)
        self.assertIn("openai 未安装", note)

    def test_allowed_models_is_exactly_default(self):
        self.assertEqual(providers.ALLOWED_MODELS, {DEFAULT_MODEL})


if __name__ == "__main__":
    unittest.main(verbosity=2)