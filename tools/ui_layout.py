#!/usr/bin/env python3
"""Tk 布局辅助：屏幕适配、整页滚动（类似网页单滚动条）。"""

from __future__ import annotations

import tkinter as tk
import weakref
from tkinter import ttk
from typing import Any

PREFER_WINDOW_W = 1280
PREFER_WINDOW_H = 840

# 全局滚轮：多窗口共享 bind_all，按栈顶 ScrollableFrame 分发
_wheel_frames: list[weakref.ReferenceType[Any]] = []
_wheel_bound = False


def _global_mousewheel(evt: tk.Event) -> str | None:
    for ref in reversed(_wheel_frames):
        frame = ref()
        if frame is None:
            continue
        try:
            if not frame.winfo_exists():
                continue
        except tk.TclError:
            continue
        result = frame._handle_mousewheel(evt)
        if result == "break":
            return "break"
    return None


def _ensure_wheel_bound() -> None:
    global _wheel_bound
    if _wheel_bound:
        return
    root = tk._get_default_root()
    if root is None:
        return
    root.bind_all("<MouseWheel>", _global_mousewheel, add="+")
    root.bind_all("<Button-4>", _global_mousewheel, add="+")
    root.bind_all("<Button-5>", _global_mousewheel, add="+")
    _wheel_bound = True


def _cleanup_wheel_registry() -> None:
    global _wheel_frames, _wheel_bound
    _wheel_frames = [r for r in _wheel_frames if r() is not None]
    if _wheel_frames:
        return
    if not _wheel_bound:
        return
    root = tk._get_default_root()
    if root is None:
        _wheel_bound = False
        return
    try:
        root.unbind_all("<MouseWheel>")
        root.unbind_all("<Button-4>")
        root.unbind_all("<Button-5>")
    except tk.TclError:
        pass
    _wheel_bound = False


class ScrollableFrame(ttk.Frame):
    """整页垂直滚动：单一滚动条，滚轮在内部任意控件上均滚动整页。"""

    def __init__(self, parent: Any, *, wheel_exempt: tuple[Any, ...] = (), **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self._wheel_exempt = wheel_exempt
        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self._vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self.interior = ttk.Frame(self._canvas)
        self._win_id = self._canvas.create_window((0, 0), window=self.interior, anchor=tk.NW)
        self._canvas.configure(yscrollcommand=self._vsb.set)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.interior.bind("<Configure>", self._on_interior_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._wheel_registered = False
        self._refresh_job: str | None = None
        self._refresh_suspended = 0
        self.bind("<Destroy>", self._on_destroy, add="+")

    def install_global_wheel(self) -> None:
        """绑定全局滚轮：在页面内任意位置滚动整页（类似网页）。"""
        if self._wheel_registered:
            return
        self._wheel_registered = True
        _wheel_frames.append(weakref.ref(self))
        _ensure_wheel_bound()

    def uninstall_global_wheel(self) -> None:
        if not self._wheel_registered:
            return
        self._wheel_registered = False
        global _wheel_frames
        _wheel_frames = [r for r in _wheel_frames if r() is not self]
        _cleanup_wheel_registry()

    def _on_destroy(self, evt: tk.Event) -> None:
        if evt.widget is self:
            self._cancel_refresh_job()
            self.uninstall_global_wheel()

    def contains_widget(self, widget: tk.Misc | None) -> bool:
        w: tk.Misc | None = widget
        while w is not None:
            if w == self.interior or w == self._canvas or w == self:
                return True
            w = w.master  # type: ignore[assignment]
        return False

    def _is_wheel_exempt(self, widget: tk.Misc | None) -> bool:
        w: tk.Misc | None = widget
        while w is not None:
            if w in self._wheel_exempt:
                return True
            w = w.master  # type: ignore[assignment]
        return False

    def scroll_units(self, delta: int) -> None:
        try:
            if not self.winfo_exists() or self._canvas.winfo_height() <= 1:
                return
            self._canvas.yview_scroll(delta, "units")
        except tk.TclError:
            pass

    def suspend_refresh(self) -> None:
        """批量更新子控件时暂停 scrollregion 重算（避免左侧点选卡顿）。"""
        self._refresh_suspended += 1

    def resume_refresh(self) -> None:
        if self._refresh_suspended <= 0:
            return
        self._refresh_suspended -= 1
        if self._refresh_suspended == 0:
            self.refresh(immediate=True)

    def refresh(self, *, immediate: bool = False) -> None:
        """更新 scrollregion；默认防抖，避免列表批量插入时反复 layout。"""
        if self._refresh_suspended > 0 and not immediate:
            return
        if immediate:
            self._cancel_refresh_job()
            self._do_refresh()
            return
        if self._refresh_job is not None:
            return
        try:
            self._refresh_job = self.after(48, self._run_deferred_refresh)
        except tk.TclError:
            pass

    def _cancel_refresh_job(self) -> None:
        job = self._refresh_job
        self._refresh_job = None
        if job is None:
            return
        try:
            self.after_cancel(job)
        except tk.TclError:
            pass

    def _run_deferred_refresh(self) -> None:
        self._refresh_job = None
        self._do_refresh()

    def _do_refresh(self) -> None:
        try:
            if not self.winfo_exists():
                return
            bbox = self._canvas.bbox("all")
            if bbox:
                self._canvas.configure(scrollregion=bbox)
        except tk.TclError:
            pass

    def _on_interior_configure(self, _evt: tk.Event | None = None) -> None:
        self.refresh()

    def _on_canvas_configure(self, evt: tk.Event) -> None:
        try:
            self._canvas.itemconfigure(self._win_id, width=evt.width)
        except tk.TclError:
            pass

    def _handle_mousewheel(self, evt: tk.Event) -> str | None:
        if not self.contains_widget(evt.widget):
            return None
        if self._is_wheel_exempt(evt.widget):
            return None
        if getattr(evt, "delta", 0):
            delta = int(-1 * (evt.delta / 120)) or (-1 if evt.delta > 0 else 1)
        elif evt.num == 4:
            delta = -1
        elif evt.num == 5:
            delta = 1
        else:
            return None
        self.scroll_units(delta)
        return "break"


def fit_toplevel_to_screen(
    win: tk.Misc,
    *,
    prefer_w: int = PREFER_WINDOW_W,
    prefer_h: int = PREFER_WINDOW_H,
    min_w: int = 720,
    min_h: int = 480,
    margin: int = 56,
) -> tuple[int, int]:
    """将窗口尺寸限制在屏幕可用区域内并居中。"""
    try:
        win.update_idletasks()
        sw = int(win.winfo_screenwidth())
        sh = int(win.winfo_screenheight())
    except tk.TclError:
        return prefer_w, prefer_h
    w = max(min_w, min(prefer_w, sw - margin))
    h = max(min_h, min(prefer_h, sh - margin))
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    if isinstance(win, (tk.Tk, tk.Toplevel)):
        try:
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.minsize(min(min_w, w), min(min_h, h))
        except tk.TclError:
            pass
    return w, h
