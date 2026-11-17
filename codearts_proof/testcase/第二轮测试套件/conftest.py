# -*- coding: utf-8 -*-
"""pytest 全局配置（pytest 专用；unittest 直接运行时不依赖本文件）。

两件事：
1. 把源码目录加入 sys.path —— 生产代码用的是裸导入（``import prompts``）。
2. 每个用例前清空真实模型相关环境变量 —— 测试绝不允许打到外部模型接口。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import _asyncio_compat  # noqa: E402,F401  （选择 socket-free 事件循环）

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
    """默认让每个用例处于“无 MODE、无 KEY”的干净状态（auto 模式降级回放）。"""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield