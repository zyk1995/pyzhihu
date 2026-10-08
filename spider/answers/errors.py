#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取过程中抛给命令行的错误。"""


class ZhihuError(Exception):
    """请求、解析或参数不合法。"""


class ZhihuBlockedError(ZhihuError):
    """知乎拒绝本次访问，通常需要浏览器 Cookie 或更换网络。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: int | str | None = None,
        body: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.body = body
