"""Telegram Bot API client (sendMessage, MarkdownV2)."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("rh_meme_watch.telegram")

API_BASE = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


class TelegramAuthError(TelegramError):
    pass


class TelegramClient:
    def __init__(
        self,
        token: str,
        chat_id: str,
        http: httpx.Client | None = None,
        api_base: str = API_BASE,
    ) -> None:
        self._own_http = http is None
        self.http = http or httpx.Client(timeout=httpx.Timeout(20.0))
        self.token = token
        self.chat_id = chat_id
        self.api_base = api_base.rstrip("/")

    def close(self) -> None:
        if self._own_http:
            self.http.close()

    def _call(self, method: str, payload: dict) -> dict:
        url = f"{self.api_base}/bot{self.token}/{method}"
        try:
            resp = self.http.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise TelegramError(f"{method}: transport error: {exc!r}") from exc
        if resp.status_code in (401, 403):
            raise TelegramAuthError(f"{method}: HTTP {resp.status_code} (bad token?)")
        try:
            body = resp.json()
        except ValueError as exc:
            raise TelegramError(f"{method}: invalid JSON (HTTP {resp.status_code})") from exc
        if resp.status_code != 200 or not body.get("ok"):
            raise TelegramError(
                f"{method}: HTTP {resp.status_code}: {body.get('description', 'unknown error')}"
            )
        return body

    def verify(self) -> dict:
        """getMe; raises TelegramAuthError on bad credentials."""
        return self._call("getMe", {})

    def send(self, text: str) -> None:
        self._call(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            },
        )
