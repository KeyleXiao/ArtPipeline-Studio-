#!/usr/bin/env python3
"""ArtPipeline 客户端视觉主题（ttkbootstrap / tk）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
APP_ICON_PATH = TOOLS_DIR / "assets" / "app_icon.png"

# 深色产品化配色
BG_APP = "#1a1a1e"
BG_SURFACE = "#232328"
BG_ELEVATED = "#2c2c32"
BG_INPUT = "#1e1e24"
FG_PRIMARY = "#f2f2f7"
FG_MUTED = "#8e8e98"
FG_HINT = "#6a6a75"
ACCENT = "#6c8cff"
ACCENT_OK = "#3dd68c"
ACCENT_WARN = "#ffb020"
ACCENT_ERR = "#ff6b6b"
BORDER = "#3a3a42"

FONT_UI = ("Helvetica Neue", 12)
FONT_UI_SM = ("Helvetica Neue", 11)
FONT_TITLE = ("Helvetica Neue", 20, "bold")
FONT_SUBTITLE = ("Helvetica Neue", 11)
FONT_SECTION = ("Helvetica Neue", 12, "bold")
FONT_MONO = ("Menlo", 11)
FONT_MONO_SM = ("Menlo", 10)

PRODUCT_NAME = "ArtPipeline Studio @keyke"
PRODUCT_TAGLINE = "游戏美术流水线 · 本地 ComfyUI"


def load_app_icon_photos(root: Any) -> dict[str, Any]:
    """加载窗口与顶栏图标；返回 PhotoImage 引用字典（须挂到 root 防 GC）。"""
    photos: dict[str, Any] = {}
    if not APP_ICON_PATH.is_file():
        return photos
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return photos
    try:
        base = Image.open(APP_ICON_PATH).convert("RGBA")
        for key, size in (("window", 64), ("brand", 40)):
            im = base.copy()
            im.thumbnail((size, size), Image.Resampling.LANCZOS)
            photos[key] = ImageTk.PhotoImage(im)
        if "window" in photos:
            root.iconphoto(True, photos["window"])
    except Exception:
        return {}
    return photos


def apply_app_styles(root: Any, *, has_ttb: bool) -> None:
    """应用全局 ttk / tk 样式。"""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        return

    if has_ttb:
        try:
            style = ttk.Style()
            style.configure(".", font=FONT_UI)
            style.configure("BrandTitle.TLabel", font=FONT_TITLE, foreground=FG_PRIMARY)
            style.configure("BrandSubtitle.TLabel", font=FONT_SUBTITLE, foreground=FG_MUTED)
            style.configure("Section.TLabel", font=FONT_SECTION, foreground=FG_PRIMARY)
            style.configure("Muted.TLabel", font=FONT_UI_SM, foreground=FG_MUTED)
            style.configure("Hint.TLabel", font=FONT_UI_SM, foreground=FG_HINT)
            style.configure("Status.TLabel", font=FONT_UI_SM, foreground=FG_MUTED)
            style.configure("Treeview", rowheight=30, font=FONT_UI_SM, background=BG_ELEVATED, fieldbackground=BG_ELEVATED)
            style.configure(
                "Treeview.Heading",
                font=(FONT_UI_SM[0], FONT_UI_SM[1], "bold"),
                background=BG_SURFACE,
                foreground=FG_MUTED,
            )
            style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])
        except Exception:
            pass

    try:
        root.configure(bg=BG_APP if has_ttb else root.cget("bg"))
    except Exception:
        pass


def style_listbox(listbox: Any) -> None:
    listbox.configure(
        bg=BG_ELEVATED,
        fg=FG_PRIMARY,
        selectbackground=ACCENT,
        selectforeground="#ffffff",
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
        borderwidth=0,
        font=FONT_UI_SM,
        activestyle="none",
    )


def style_text_widget(text: Any, *, mono: bool = False, height_bg: bool = False) -> None:
    bg = BG_INPUT if height_bg else BG_ELEVATED
    text.configure(
        bg=bg,
        fg=FG_PRIMARY,
        insertbackground=FG_PRIMARY,
        selectbackground=ACCENT,
        selectforeground="#ffffff",
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
        font=FONT_MONO if mono else FONT_UI_SM,
        padx=8,
        pady=6,
    )


def style_preview_label(label: Any) -> None:
    label.configure(
        bg=BG_INPUT,
        fg=FG_MUTED,
        highlightthickness=1,
        highlightbackground=BORDER,
    )
