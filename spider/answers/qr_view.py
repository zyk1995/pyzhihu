#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在终端画出二维码，并另存一张 PNG。不打开图片查看器。"""

from __future__ import annotations

import io
import os
from pathlib import Path

import segno

from spider.answers.errors import ZhihuError


def render_terminal_qr(data: str) -> str:
    """用 Unicode 方块把二维码画成纯文本，SSH 里也能看。"""
    if not data:
        raise ZhihuError("没有可编码的登录链接")
    buffer = io.StringIO()
    segno.make(data, error="m").terminal(out=buffer, compact=True)
    text = buffer.getvalue()
    if "█" not in text:
        raise ZhihuError("终端二维码生成失败")
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_qr_png(data: str, path: Path, *, official_png: bytes | None = None) -> None:
    """保存 PNG 备用。优先用官方图片字节，否则按链接本地生成。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    if official_png and official_png.startswith(b"\x89PNG"):
        path.write_bytes(official_png)
    else:
        segno.make(data, error="m").save(path, scale=6, border=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def emit_terminal_qr(text: str, write) -> None:
    """写到给定输出。编码装不下方块字符时只提示去看 PNG。"""
    encoding = getattr(write, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        write("当前终端编码无法显示字符二维码，请把保存的 PNG 下载到本地查看。\n")
        return
    write(text)
