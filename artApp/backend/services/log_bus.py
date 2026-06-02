#!/usr/bin/env python3
"""内存日志总线（生成 / 操作 / 系统），可选写入磁盘。"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

MAX_ENTRIES = 2000
LOG_FILE_NAME = "studio.log"
LOG_ROTATE_BYTES = 5_000_000
_LINE_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] \[(?P<kind>[^\]]+)\] (?P<msg>.*)$")


class LogBus:
    def __init__(self) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=MAX_ENTRIES)
        self._lock = threading.Lock()
        self._queues: list[asyncio.Queue[dict[str, Any] | None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._log_dir: Path | None = None
        self._log_file: Path | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def configure(self, log_dir: Path) -> None:
        """设置日志目录并尝试从 studio.log 尾部恢复最近记录。"""
        resolved = log_dir.expanduser().resolve()
        with self._lock:
            if self._log_dir == resolved:
                return
            self._log_dir = resolved
            self._log_file = resolved / LOG_FILE_NAME
        try:
            resolved.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._tail_from_file()

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
        self._append_file(entry)
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

    def log_file_path(self) -> Path | None:
        return self._log_file

    def _append_file(self, entry: dict[str, Any]) -> None:
        log_file = self._log_file
        if not log_file:
            return
        ts_full = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["ts_epoch"]))
        line = f"[{ts_full}] [{entry['kind']}] {entry['msg']}\n"
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            if log_file.is_file() and log_file.stat().st_size >= LOG_ROTATE_BYTES:
                backup = log_file.with_suffix(".log.1")
                if backup.is_file():
                    backup.unlink()
                log_file.rename(backup)
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def _tail_from_file(self, max_lines: int = 400) -> None:
        log_file = self._log_file
        if not log_file or not log_file.is_file():
            return
        try:
            text = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        lines = text.splitlines()[-max_lines:]
        restored: list[dict[str, Any]] = []
        for line in lines:
            parsed = self._parse_line(line)
            if parsed:
                restored.append(parsed)
        if not restored:
            return
        with self._lock:
            if self._entries:
                return
            for item in restored:
                self._entries.append(item)

    @staticmethod
    def _parse_line(line: str) -> dict[str, Any] | None:
        m = _LINE_RE.match(line.strip())
        if not m:
            return None
        ts_full = m.group("ts")
        try:
            ts_epoch = time.mktime(time.strptime(ts_full, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            ts_epoch = time.time()
        short_ts = ts_full.split(" ", 1)[-1] if " " in ts_full else ts_full
        return {
            "ts": short_ts,
            "ts_epoch": ts_epoch,
            "kind": m.group("kind"),
            "msg": m.group("msg"),
        }


log_bus = LogBus()
