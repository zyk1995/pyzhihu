#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取过程中抛给命令行的错误。"""


class ZhihuError(Exception):
    """请求、解析或参数不合法。"""


class ZhihuBlockedError(ZhihuError):
    """知乎拒绝本次访问，通常要重新扫码、降低频率或更换网络。"""

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


def is_login_failure(exc: ZhihuBlockedError) -> bool:
    """登录过期或未登录。频率限制和安全验证不算登录失效。"""
    if exc.error_code in (401, 40353):
        return True
    text = str(exc)
    if exc.error_code in (40362, 40352, "zse-ck"):
        return False
    return "登录" in text


def explain_block(status: int | None, code: int | str | None, raw_message: str) -> str:
    """把知乎的拒绝原因说成可操作的中文。"""
    lines = [
        f"知乎拒绝了访问（HTTP {status}，错误码 {code}）。",
        f"接口原文：{raw_message}",
    ]
    if status == 429 or code == 429:
        lines.append("请求过于频繁。请把 --delay 调大（例如 2 或 3）后再运行，已经保存的回答会接着抓。")
    elif code == 40353 or ("登录" in raw_message and code not in (40362, 40352)):
        lines.append("登录已失效，或当前没有登录。重新运行会提示扫码；也可以直接加上 --login。")
        lines.append("若要自己贴 Cookie，用环境变量 ZHIHU_COOKIE 或 --cookie-file。")
    elif code == 40352 or "验证" in raw_message:
        lines.append("知乎要求安全验证，当前网络被拦截。请换一个网络后再扫码，或在浏览器完成验证后用 --cookie-file 提供 Cookie。")
    elif code == 40362:
        lines.append("知乎认为这次请求异常，多半是访问太密或机房网络。请加大 --delay 后重试。")
        lines.append("也可以改用 ZHIHU_COOKIE 或 --cookie-file；登录过期时加上 --login 重新扫码。")
    elif code == "zse-ck":
        lines.append("当前网络触发了知乎的校验页。请换网络，或用 --login / ZHIHU_COOKIE 提供登录态。")
    else:
        lines.append("可以加上 --login 扫码，或用 ZHIHU_COOKIE / --cookie-file 提供 Cookie。")
    return "\n".join(lines)


def explain_rate_limit(retries: int) -> str:
    return (
        f"请求过于频繁（HTTP 429），已重试 {retries} 次。"
        "请把 --delay 调大后再运行，已经写入的回答会从进度文件继续。"
    )
