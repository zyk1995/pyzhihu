#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把扫码得到的 Cookie 存到用户目录，权限收成仅本人可读。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from spider.answers.cookie import read_cookie_file

_LOGIN_COOKIE = re.compile(r"(?:^|;)\s*z_c0=")


def default_session_path() -> Path:
    return Path.home() / ".config" / "zhihu-spider" / "session.cookie"


def has_login_cookie(cookie: str) -> bool:
    return bool(_LOGIN_COOKIE.search(cookie or ""))


def load_session(path: Path) -> str:
    if not path.exists():
        return ""
    return read_cookie_file(path)


def save_session(path: Path, cookie: str) -> None:
    text = (cookie or "").strip()
    if not text:
        raise OSError("没有可保存的 Cookie")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
