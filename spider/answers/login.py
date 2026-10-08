#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知乎官方二维码登录。终端显示字符二维码，PNG 只作备份。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

from spider.answers.client import USER_AGENT
from spider.answers.errors import ZhihuBlockedError, ZhihuError, explain_block
from spider.answers.qr_view import emit_terminal_qr, render_terminal_qr, write_qr_png
from spider.answers.session_store import save_session
from spider.answers.sign import sign_path

SIGNIN_URL = "https://www.zhihu.com/signin?next=%2F"
UDID_URL = "https://www.zhihu.com/udid"
CAPTCHA_URL = "https://www.zhihu.com/api/v3/oauth/captcha?lang=cn"
QR_URL = "https://www.zhihu.com/api/v3/account/api/login/qrcode"

PROMPTS = {
    "waiting": "等待扫码。请用知乎 App 扫描上面的字符二维码，并在手机上确认。",
    "scanned": "已扫码请在手机确认。",
    "expired": "二维码过期自动刷新。",
    "success": "登录成功。",
}


@dataclass
class QrTicket:
    token: str
    link: str
    expires_at: float


@dataclass
class ScanPoll:
    status_code: int
    payload: dict | None
    has_z_c0: bool


def interpret_scan(poll: ScanPoll) -> str:
    """把一次轮询结果收成 waiting / scanned / success / expired / blocked / retry。"""
    if poll.has_z_c0:
        return "success"
    payload = poll.payload if isinstance(poll.payload, dict) else None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "")
        code = error.get("code")
        if "过期" in message or "失效" in message:
            return "expired"
        if "验证码" in message or code in (40352, 40362, 40353, 4039) or poll.status_code in (401, 403):
            return "blocked"
        return "blocked" if poll.status_code >= 400 else "retry"
    if poll.status_code == 429:
        return "retry"
    if poll.status_code in (401, 403):
        return "blocked"
    if not isinstance(payload, dict):
        return "retry" if poll.status_code >= 500 else "blocked"
    status = payload.get("status")
    if status in (0, "0"):
        return "waiting"
    if status in (1, "1"):
        return "scanned"
    login_status = str(payload.get("login_status") or "").strip().upper()
    if login_status in {"CONFIRMED", "LOGIN_SUCCESS", "SUCCESS", "OK", "LOGGED_IN"}:
        return "success"
    if payload.get("access_token") or payload.get("success") is True:
        return "success"
    if status in (2, "2", 5, "5"):
        return "success"
    return "waiting"


def normalize_expiry(value: object, now: float) -> float:
    if isinstance(value, (int, float)) and value > 0:
        stamp = float(value)
        if stamp > 10**12:
            stamp /= 1000.0
        return stamp
    return now + 110


class HttpQrApi:
    """走知乎网页登录用的那组接口，不启动浏览器。"""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        proxy: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()
        self.proxies = {"http": proxy, "https": proxy} if proxy else None

    def bootstrap(self) -> None:
        response = self.session.get(
            SIGNIN_URL,
            headers=self._headers(json_accept=False),
            timeout=self.timeout,
            proxies=self.proxies,
            allow_redirects=True,
        )
        if not self.session.cookies.get("_xsrf"):
            if "zh-zse-ck" in (response.text or "") or "安全验证" in (response.text or ""):
                raise ZhihuBlockedError(
                    explain_block(response.status_code, "zse-ck", "登录页返回了安全验证，没有拿到 _xsrf"),
                    status_code=response.status_code,
                    error_code="zse-ck",
                    body=(response.text or "")[:500],
                )
            raise ZhihuError("没有拿到登录页的 _xsrf，无法发起扫码。请换一个网络后再试。")
        self.session.post(UDID_URL, headers=self._headers(), timeout=self.timeout, proxies=self.proxies)
        captcha = self.session.get(CAPTCHA_URL, headers=self._headers(), timeout=self.timeout, proxies=self.proxies)
        payload = _json_dict(captcha.text)
        if isinstance(payload, dict):
            _apply_cookie_directive(self.session, str(payload.get("cookie") or ""))
            if payload.get("show_captcha") is True:
                raise ZhihuError(
                    "知乎要求验证码，当前网络不能直接扫码。"
                    "请换一个网络后再试，或在浏览器登录后用 ZHIHU_COOKIE / --cookie-file 提供 Cookie。"
                )

    def fetch_ticket(self) -> QrTicket:
        response = self.session.post(QR_URL, headers=self._headers(), timeout=self.timeout, proxies=self.proxies)
        payload = _json_dict(response.text)
        if response.status_code != 200 or not isinstance(payload, dict) or payload.get("error"):
            message = ""
            code: int | str | None = response.status_code
            if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                message = str(payload["error"].get("message") or "")
                code = payload["error"].get("code", code)
            raise ZhihuBlockedError(
                explain_block(response.status_code, code, message or "获取二维码失败"),
                status_code=response.status_code,
                error_code=code,
                body=(response.text or "")[:500],
            )
        token = str(payload.get("token") or "")
        link = str(payload.get("link") or "")
        if not token or not link:
            raise ZhihuError("二维码接口没有返回 token 或登录链接")
        return QrTicket(token=token, link=link, expires_at=normalize_expiry(payload.get("expires_at"), time.time()))

    def official_image(self, token: str) -> bytes | None:
        url = f"{QR_URL}/{token}/image"
        try:
            response = self.session.get(
                url,
                headers=self._headers(json_accept=False),
                timeout=self.timeout,
                proxies=self.proxies,
            )
        except requests.RequestException:
            return None
        if response.status_code == 200 and response.content.startswith(b"\x89PNG"):
            return response.content
        return None

    def poll(self, token: str) -> ScanPoll:
        path = f"/api/v3/account/api/login/qrcode/{token}/scan_info"
        headers = self._headers()
        cookie = self.cookie_header()
        if "d_c0=" in cookie:
            try:
                signed = sign_path(path, cookie)
            except ValueError:
                signed = None
            if signed:
                headers["x-zse-93"] = signed["x-zse-93"]
                headers["x-zse-96"] = signed["x-zse-96"]
                headers["x-zst-81"] = signed["x-zst-81"]
        response = self.session.get(
            "https://www.zhihu.com" + path,
            headers=headers,
            timeout=self.timeout,
            proxies=self.proxies,
            allow_redirects=False,
        )
        _absorb_z_c0(self.session, response)
        return ScanPoll(response.status_code, _json_dict(response.text), bool(self.session.cookies.get("z_c0")))

    def cookie_header(self) -> str:
        items: dict[str, str] = {}
        for cookie in self.session.cookies:
            items[cookie.name] = cookie.value
        return "; ".join(f"{name}={value}" for name, value in items.items())

    def _headers(self, *, json_accept: bool = True) -> dict[str, str]:
        xsrf = self.session.cookies.get("_xsrf") or ""
        return {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*" if json_accept else "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": SIGNIN_URL,
            "Origin": "https://www.zhihu.com",
            "x-requested-with": "fetch",
            "x-xsrftoken": xsrf,
        }


def run_qr_login(
    api: HttpQrApi,
    png_path: Path,
    *,
    timeout: float = 300,
    poll_interval: float = 2.0,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    emit: Callable[[str], None] | None = None,
    session_path: Path | None = None,
) -> str:
    """显示二维码并轮询，直到登录成功、超时或被风控拦住。"""
    clock = now or time.time
    pause = sleep or time.sleep
    say = emit or (lambda _message: None)
    if timeout < 0:
        raise ZhihuError("--login-timeout 不能为负数")
    api.bootstrap()
    deadline = None if timeout == 0 else clock() + timeout
    while True:
        if deadline is not None and clock() >= deadline:
            raise ZhihuError("扫码等待超时。可以加大 --login-timeout 后重新运行。")
        ticket = api.fetch_ticket()
        official = api.official_image(ticket.token)
        write_qr_png(ticket.link, png_path, official_png=official)
        qr_text = render_terminal_qr(ticket.link)
        emit_terminal_qr(qr_text, say)
        say(f"二维码图片已保存：{png_path}")
        say("这是无图形界面可用的字符二维码，程序不会打开图片查看器。")
        if official is None:
            say("官方二维码图片接口没有返回 PNG，上面的码是按登录链接在本地生成的，手机知乎 App 可以扫。")
        say(PROMPTS["waiting"])
        seen = "waiting"
        while True:
            if deadline is not None and clock() >= deadline:
                raise ZhihuError("扫码等待超时。可以加大 --login-timeout 后重新运行。")
            if clock() >= ticket.expires_at:
                say(PROMPTS["expired"])
                break
            poll = api.poll(ticket.token)
            kind = interpret_scan(poll)
            if kind == "success":
                cookie = api.cookie_header()
                if "z_c0=" not in cookie:
                    raise ZhihuError("扫码接口表示成功，但响应里没有 z_c0，登录没有完成。")
                if session_path is not None:
                    save_session(session_path, cookie)
                say(PROMPTS["success"])
                if session_path is not None:
                    say(f"会话已保存：{session_path}")
                return cookie
            if kind == "blocked":
                message = ""
                code: int | str | None = poll.status_code
                if isinstance(poll.payload, dict) and isinstance(poll.payload.get("error"), dict):
                    message = str(poll.payload["error"].get("message") or "")
                    code = poll.payload["error"].get("code", code)
                raise ZhihuBlockedError(
                    explain_block(poll.status_code, code, message or "轮询扫码状态被拒绝")
                    + f"\n字符二维码已经显示，图片在 {png_path}。本次没能确认手机是否扫过。"
                    "请换网络后重新运行；不要连续重试。",
                    status_code=poll.status_code,
                    error_code=code,
                )
            if kind == "expired":
                say(PROMPTS["expired"])
                break
            if kind == "scanned" and seen != "scanned":
                say(PROMPTS["scanned"])
                seen = "scanned"
            elif kind == "waiting" and seen != "waiting":
                say(PROMPTS["waiting"])
                seen = "waiting"
            pause(poll_interval)


def _json_dict(text: str) -> dict | None:
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _apply_cookie_directive(session: requests.Session, directive: str) -> None:
    if not directive or "=" not in directive:
        return
    pair = directive.split(";", 1)[0]
    name, value = pair.split("=", 1)
    name = name.strip()
    if name and not session.cookies.get(name):
        session.cookies.set(name, value.strip(), domain=".zhihu.com")


def _absorb_z_c0(session: requests.Session, response: requests.Response) -> None:
    for cookie in response.cookies:
        if cookie.name == "z_c0":
            session.cookies.set("z_c0", cookie.value, domain=cookie.domain or ".zhihu.com")
    payload = _json_dict(response.text or "")
    if isinstance(payload, dict) and payload.get("z_c0") and not session.cookies.get("z_c0"):
        session.cookies.set("z_c0", str(payload["z_c0"]), domain=".zhihu.com")
