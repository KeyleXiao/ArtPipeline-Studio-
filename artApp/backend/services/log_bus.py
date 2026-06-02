#!/usr/bin/env python3
"""内存日志总线（生成 / 操作 / 系统）。"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Any

MAX_ENTRIES = 2000


class LogBus:
    def __init__(self) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=MAX_ENTRIES)
        self._lock = threading.Lock()
        self._queues: list[asyncio.Queue[dict[str, Any] | None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @staticmethod
    def infer_kind(msg: str) -> str:
        if any(k in msg for k in ("ComfyUI", "checkpoint", "UI 回调", "工具已启动", "配置文件:", "扫描")):
            return "系统"
        if any(k in msg for k in ("生成", "FAIL", "source →", "inbox", "导出", "ComfyUI")):
            return "生成"
        return "操作"

    def log(self, msg: str, *, kind: str | None = None) -> dict[str, Any]:
        now = time.time()
        entry = {
            "ts": time.strftime("%H:%M:%S", time.localtime(now)),
            "ts_epoch": now,
            "kind": kind or self.infer_kind(msg),
            "msg": msg,
        }
        with self._lock:
            self._entries.append(entry)
            queues = list(self._queues)
        for q in queues:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                pass
        return entry

    def history(self, *, tab: str = "全部", limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._entries)
        if tab != "全部":
            items = [e for e in items if e["kind"] == tab]
        return items[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def subscribe(self) -> asyncio.Queue[dict[str, Any] | None]:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        with self._lock:
            self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any] | None]) -> None:
        with self._lock:
            self._queues = [x for x in self._queues if x is not q]


log_bus = LogBus()
