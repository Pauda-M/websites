"""Telegram startup contract: verify credentials, announce, exit non-zero on auth failure."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from rh_meme_watch.__main__ import main
from rh_meme_watch.telegram import TelegramAuthError, TelegramClient

TOKEN = "123456:TEST-TOKEN"
GETME = f"https://api.telegram.org/bot{TOKEN}/getMe"
SEND = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


@respx.mock
def test_verify_raises_on_401():
    respx.post(GETME).mock(
        return_value=httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    )
    client = TelegramClient(TOKEN, "5182460904", http=httpx.Client())
    with pytest.raises(TelegramAuthError):
        client.verify()


@respx.mock
def test_send_uses_markdown_v2():
    respx.post(GETME).mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"username": "b"}})
    )
    send_route = respx.post(SEND).mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {}})
    )
    client = TelegramClient(TOKEN, "5182460904", http=httpx.Client())
    client.verify()
    client.send("hello")
    body = json.loads(send_route.calls[0].request.content)
    assert body["parse_mode"] == "MarkdownV2"
    assert body["chat_id"] == "5182460904"


@respx.mock
def test_main_exits_nonzero_when_telegram_auth_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    respx.post(GETME).mock(
        return_value=httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    )
    assert main() == 1


def test_main_exits_nonzero_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert main() == 2


@respx.mock
def test_startup_announcement_sent(tmp_path, monkeypatch):
    """getMe ok -> the up-message goes out (loop itself is not started here)."""
    from rh_meme_watch.app import App
    from conftest import mk_cfg

    respx.post(GETME).mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"username": "b"}})
    )
    send_route = respx.post(SEND).mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {}})
    )
    cfg = mk_cfg(tmp_path)
    app = App(cfg, telegram=TelegramClient(TOKEN, cfg.telegram_chat_id, http=httpx.Client()))
    app.startup()
    body = json.loads(send_route.calls[0].request.content)
    assert body["text"].replace("\\", "") == (
        "rh-meme-watch up · floor $150k / stock $75k · poll 60s"
    )
