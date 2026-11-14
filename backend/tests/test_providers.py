# -*- coding: utf-8 -*-
"""providers 模块单元测试。

覆盖点：
- parse_level：LEVEL 行解析（高/中/低）、关键词加权投票、同分偏严重、
  "位置："兜底升级、空输入默认档
- strip_level：只剥掉首个 LEVEL 行
- MaasProvider：模型白名单硬约束、缺 Key、client 构造参数、complete 的请求参数
  与空正文回退（全部不发起真实网络请求）
- build_provider：replay / maas / auto 三种模式与初始化失败降级
- ReplayProvider：marker 匹配与 complete 返回

说明：所有涉及真实模型的路径都用 monkeypatch 替换 ``openai.AsyncOpenAI``，
测试过程中不会产生任何外部网络调用。
"""
import asyncio
from types import SimpleNamespace

import pytest

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


# --------------------------------------------------------------------------- #
# 等级解析
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("LEVEL: 高", "high"),
        ("LEVEL: 低", "low"),
        ("LEVEL: 中", "mid"),
        ("等级：高\n补充说明", "high"),
        ("评级: 低", "low"),
        ("LEVEL: **高**", "high"),
    ],
)
def test_parse_level_reads_explicit_level_line(text, expected):
    assert parse_level(text) == expected


def test_parse_level_without_level_line_but_has_issue_position_returns_mid():
    """没有 LEVEL 行、也没有关键词，但正文给出问题位置 —— 不能算低。"""
    text = "整体结构尚可，未见明显风险。\n位置：第 12 行"
    assert parse_level(text) == "mid"


def test_parse_level_upgrades_explicit_low_when_issue_position_present():
    """显式 LEVEL: 低，但正文列了具体问题位置 —— 应升级为 mid。"""
    text = "LEVEL: 低\n位置：第 12 行，存在可疑的 SQL 拼接"
    assert parse_level(text) == "mid"


def test_parse_level_votes_by_severe_keywords():
    text = "存在注入风险，且越权，属于严重问题，必须立即修复"
    assert parse_level(text) == "high"


def test_parse_level_votes_by_mid_keywords():
    text = "职责不单一，建议修复，整体有缺陷"
    assert parse_level(text) == "mid"


def test_parse_level_votes_by_low_keywords():
    text = "结构清晰，无问题，低风险"
    assert parse_level(text) == "low"


def test_parse_level_tie_prefers_more_severe_level():
    """high 与 mid 得分相同时偏严重档。"""
    text = "严重\n有缺陷"
    assert parse_level(text) == "high"


@pytest.mark.parametrize("text", ["", None])
def test_parse_level_empty_text_defaults_to_mid(text):
    assert parse_level(text) == "mid"


# --------------------------------------------------------------------------- #
# LEVEL 行剥离
# --------------------------------------------------------------------------- #
def test_strip_level_removes_level_line():
    assert strip_level("LEVEL: 高\n正文第一行\n正文第二行") == "正文第一行\n正文第二行"


def test_strip_level_keeps_text_without_level_line():
    assert strip_level("  正文\n第二行  ") == "正文\n第二行"


def test_strip_level_only_skips_first_matching_line():
    assert strip_level("LEVEL: 高\n正文\nLEVEL: 低") == "正文\nLEVEL: 低"


def test_strip_level_none_returns_empty_string():
    assert strip_level(None) == ""


# --------------------------------------------------------------------------- #
# MaasProvider
# --------------------------------------------------------------------------- #
class _FakeAsyncOpenAI:
    """替代 openai.AsyncOpenAI，只记录构造参数，不发请求。"""

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs


def test_maas_provider_rejects_model_outside_allowlist(monkeypatch):
    """白名单是硬约束：不在列表内的模型名必须拒绝初始化。"""
    monkeypatch.setenv("MAAS_API_KEY", "test-key")
    monkeypatch.setenv("MAAS_MODEL", "gpt-4o-mini")

    with pytest.raises(RuntimeError) as excinfo:
        MaasProvider()

    message = str(excinfo.value)
    assert "不在允许列表内" in message
    assert "'gpt-4o-mini'" in message
    assert DEFAULT_MODEL in message


def test_maas_provider_requires_api_key(monkeypatch):
    monkeypatch.setenv("MAAS_API_KEY", "   ")
    monkeypatch.setenv("MAAS_MODEL", DEFAULT_MODEL)

    with pytest.raises(RuntimeError) as excinfo:
        MaasProvider()

    assert str(excinfo.value) == "未配置 MAAS_API_KEY"


def test_maas_provider_builds_client_with_allowed_model(monkeypatch):
    monkeypatch.setenv("MAAS_API_KEY", "test-key")
    monkeypatch.setenv("MAAS_MODEL", DEFAULT_MODEL)
    monkeypatch.setenv("REVIEW_TIMEOUT", "12")
    monkeypatch.setenv("MAX_TOKENS", "512")
    monkeypatch.setattr("openai.AsyncOpenAI", _FakeAsyncOpenAI)

    provider = MaasProvider()

    assert provider.model == DEFAULT_MODEL
    assert provider.timeout == 12.0
    assert provider.max_tokens == 512
    assert provider.client.init_kwargs == {
        "api_key": "test-key",
        "base_url": DEFAULT_BASE_URL,
    }


def test_maas_provider_falls_back_to_default_model_when_blank(monkeypatch):
    monkeypatch.setenv("MAAS_API_KEY", "test-key")
    monkeypatch.setenv("MAAS_MODEL", "   ")
    monkeypatch.setattr("openai.AsyncOpenAI", _FakeAsyncOpenAI)

    assert MaasProvider().model == DEFAULT_MODEL


class _FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _provider_with_response(response):
    """绕过 __init__，直接装配一个带假 client 的 MaasProvider。"""
    provider = MaasProvider.__new__(MaasProvider)
    provider.model = DEFAULT_MODEL
    provider.timeout = 5.0
    provider.max_tokens = 2048
    completions = _FakeCompletions(response)
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    return provider, completions


def test_complete_sends_expected_request_and_strips_content():
    message = SimpleNamespace(content="  评审结果  ", reasoning_content="思考")
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    provider, completions = _provider_with_response(response)

    text = asyncio.run(provider.complete("系统提示", "用户代码"))

    assert text == "评审结果"
    assert completions.calls == [
        {
            "model": DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "用户代码"},
            ],
            "temperature": 0.3,
            "max_tokens": 2048,
        }
    ]


def test_complete_falls_back_to_reasoning_content_when_content_empty():
    message = SimpleNamespace(content="   ", reasoning_content=" 思考内容 ")
    provider, _ = _provider_with_response(
        SimpleNamespace(choices=[SimpleNamespace(message=message)])
    )

    assert asyncio.run(provider.complete("s", "u")) == "思考内容"


def test_complete_returns_empty_string_when_no_content_at_all():
    message = SimpleNamespace(content=None, reasoning_content=None)
    provider, _ = _provider_with_response(
        SimpleNamespace(choices=[SimpleNamespace(message=message)])
    )

    assert asyncio.run(provider.complete("s", "u")) == ""


def test_complete_raises_timeout_when_client_is_slow():
    class _SlowCompletions:
        async def create(self, **kwargs):
            await asyncio.sleep(0.05)
            return None

    provider, _ = _provider_with_response(None)
    provider.timeout = 0.005
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=_SlowCompletions())
    )

    with pytest.raises(TimeoutError):
        asyncio.run(provider.complete("s", "u"))


# --------------------------------------------------------------------------- #
# ReplayProvider
# --------------------------------------------------------------------------- #
def _replay_provider():
    provider = ReplayProvider.__new__(ReplayProvider)
    provider.model = "replay"
    provider.data = {
        "skills": {
            "security": {"marker": "安全评审", "text": "security 文本", "delay": 0},
            "performance": {"marker": "性能评审", "text": "performance 文本", "delay": 0},
        },
        "conflict": {"text": "conflict 文本", "delay": 0},
    }
    return provider


def test_replay_provider_init_reads_real_replay_file():
    provider = ReplayProvider()

    assert provider.mode == "replay"
    assert "replay" in provider.model
    assert set(provider.data["skills"]) >= {"security", "performance", "architecture", "standard"}


def test_replay_provider_match_by_marker():
    provider = _replay_provider()

    assert provider._match("你是安全评审专家") == "security"
    assert provider._match("你是性能评审专家") == "performance"


def test_replay_provider_match_falls_back_to_conflict():
    provider = _replay_provider()

    assert provider._match("完全无关的 system prompt") == "conflict"


def test_replay_provider_complete_returns_skill_text():
    provider = _replay_provider()

    assert asyncio.run(provider.complete("你是安全评审专家", "code")) == "security 文本"


def test_replay_provider_complete_falls_back_to_conflict_text():
    provider = _replay_provider()

    assert asyncio.run(provider.complete("未知提示", "code")) == "conflict 文本"


# --------------------------------------------------------------------------- #
# build_provider
# --------------------------------------------------------------------------- #
def test_build_provider_replay_mode_forces_replay(monkeypatch):
    monkeypatch.setenv("MODE", "replay")

    provider, note = build_provider()

    assert isinstance(provider, ReplayProvider)
    assert note == "强制回放模式"


def test_build_provider_maas_mode_forces_maas(monkeypatch):
    monkeypatch.setenv("MODE", "  MaAs  ")
    monkeypatch.setenv("MAAS_API_KEY", "test-key")
    monkeypatch.setattr("openai.AsyncOpenAI", _FakeAsyncOpenAI)

    provider, note = build_provider()

    assert isinstance(provider, MaasProvider)
    assert note == "强制真实调用"


def test_build_provider_auto_uses_maas_when_key_present(monkeypatch):
    monkeypatch.setenv("MAAS_API_KEY", "test-key")
    monkeypatch.setattr("openai.AsyncOpenAI", _FakeAsyncOpenAI)

    provider, note = build_provider()

    assert isinstance(provider, MaasProvider)
    assert note == "已连接华为云 MaaS"


def test_build_provider_auto_uses_replay_without_key():
    provider, note = build_provider()

    assert isinstance(provider, ReplayProvider)
    assert "未配置 MAAS_API_KEY" in note


def test_build_provider_auto_downgrades_when_maas_init_fails(monkeypatch):
    monkeypatch.setenv("MAAS_API_KEY", "test-key")

    def _broken_async_openai(**kwargs):
        raise ImportError("openai 未安装")

    monkeypatch.setattr("openai.AsyncOpenAI", _broken_async_openai)

    provider, note = build_provider()

    assert isinstance(provider, ReplayProvider)
    assert "降级回放" in note
    assert "openai 未安装" in note


def test_allowed_models_only_contains_default():
    assert providers.ALLOWED_MODELS == {DEFAULT_MODEL}