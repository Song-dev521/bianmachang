# -*- coding: utf-8 -*-
"""沙箱兼容层：在不允许任何 socket 的环境里运行 asyncio 协程。

背景：
- Windows 的 ProactorEventLoop / SelectorEventLoop 初始化时都会调用
  ``socket.socketpair()`` 建立 self-pipe 自唤醒管道；
- 受限沙箱会拦截该调用（``WinError 10051``），导致 ``asyncio.run()`` 直接失败。

处理方式：
- 用 ``_NullSelector`` 顶替真实 selector（测试里没有 IO 等待，只有协程调度）；
- 去掉 self-pipe 的创建/关闭/唤醒（不注册 fd，也就不会触发 socket 系统调用）；
- 事件循环本身仍是 ``asyncio.SelectorEventLoop``，Task / Future / Queue / gather /
  wait_for 等调度语义完全由标准库真实实现，仅剥离了 IO 能力。

因此测试执行的是真实协程调度，而不是对 asyncio 的伪实现。
"""
import asyncio
import selectors
import sys
import time


class _NullSelector(selectors.BaseSelector):
    """没有任何 fd 的 selector：select() 立即返回，绝不阻塞、绝不创建 socket。"""

    def __init__(self):
        self._map = {}

    def register(self, fileobj, events, data=None):
        fd = fileobj if isinstance(fileobj, int) else fileobj.fileno()
        key = selectors.SelectorKey(fileobj, fd, events, data)
        self._map[fileobj] = key
        return key

    def unregister(self, fileobj):
        return self._map.pop(fileobj)

    def get_map(self):
        return self._map

    def select(self, timeout=None):
        # 有定时器时短暂让出 CPU，避免纯忙等；无定时器（timeout=None）时立即返回。
        if timeout:
            time.sleep(min(timeout, 0.0002))
        return []

    def close(self):
        self._map.clear()


class SocketFreeSelectorEventLoop(asyncio.SelectorEventLoop):
    """去掉 self-pipe 的 Selector 事件循环。"""

    def __init__(self, selector=None):
        # 3.12 起 BaseSelectorEventLoop 直接使用 selectors.DefaultSelector()，
        # 因此必须显式注入无 fd 的 selector。
        super().__init__(selector=_NullSelector())

    def _make_selector(self):
        return _NullSelector()

    def _make_self_pipe(self):
        self._ssock = None
        self._csock = None

    def _close_self_pipe(self):
        self._ssock = None
        self._csock = None

    def _write_to_self(self):
        return None


class SocketFreeEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    def new_event_loop(self):
        return SocketFreeSelectorEventLoop()


def install():
    """把当前平台的默认策略替换为无 socket 策略（测试进程内生效即可）。"""
    asyncio.set_event_loop_policy(SocketFreeEventLoopPolicy())


install()