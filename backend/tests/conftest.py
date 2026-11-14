# -*- coding: utf-8 -*-
"""pytest 全局配置。

两件事：
1. 把 backend 目录加入 sys.path —— 生产代码用的是裸导入（``import prompts``），
   pytest 默认只把 tests 目录放进 sys.path，不处理 backend 本身。
2. 每个用例执行前清空真实模型相关的环境变量 —— backend/.env 里配置了真实
   MAAS_API_KEY 与 MODE=maas，测试绝不允许真的打到外部模型接口。
"""
import asyncio
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no branch
    # 受限环境（沙箱/CI）下 ProactorEventLoop 的 IOCP self-pipe 可能无法建立，
    # 会让所有 async 用例直接抛 OSError。测试只用内存 ASGI 传输，
    # 不需要 IOCP 网络能力，统一切到官方支持的 Selector 策略。
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 会被 backend/.env 注入、进而影响 provider 选择的环境变量
ENV_KEYS = (
    "MODE",
    "MAAS_API_KEY",
    "MAAS_MODEL",
    "MAAS_BASE_URL",
    "REVIEW_TIMEOUT",
    "MAX_TOKENS",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """默认让每个用例处于"无 MODE、无 KEY"的干净状态（auto 模式降级回放）。"""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield