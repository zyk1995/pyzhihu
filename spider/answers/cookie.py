#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取用户自己的浏览器 Cookie，并保证里面有 d_c0。"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path

from spider.answers.sign import extract_d_c0


def read_cookie_file(path: str | os.PathLike[str]) -> str:
    """读取 Cookie 文件。

    支持两种写法：一整行浏览器请求头，或每个 ``name=value`` 占一行。
    ``#`` 开头的行视为注释。
    """
    text = Path(path).read_text(encoding="utf-8")
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    return "; ".join(lines)


def load_cookie(cookie_file: str | None = None) -> str:
    """按「命令行文件 > ZHIHU_COOKIE > ZHIHU_COOKIE_FILE」读取 Cookie。"""
    if cookie_file:
        return read_cookie_file(cookie_file)
    env_cookie = os.environ.get("ZHIHU_COOKIE", "").strip()
    if env_cookie:
        return env_cookie
    env_file = os.environ.get("ZHIHU_COOKIE_FILE", "").strip()
    if env_file:
        return read_cookie_file(env_file)
    return ""


def ensure_d_c0(cookie: str) -> tuple[str, bool]:
    """返回带 d_c0 的 Cookie，以及是否是本地补出来的。

    签名必须带上 d_c0。用户没有提供时，生成一个仅用于本次进程的值。
    知乎经常拒绝这种本地值，调用方需要把这一点告诉用户。
    """
    cookie = (cookie or "").strip().strip(";")
    try:
        extract_d_c0(cookie)
    except ValueError:
        value = f'"{secrets.token_urlsafe(18)}|{int(time.time())}"'
        piece = f"d_c0={value}"
        if cookie:
            return f"{cookie}; {piece}", True
        return piece, True
    return cookie, False
