from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.error import URLError

import pytest

from ikea_sniper import telegram
from ikea_sniper.errors import TelegramDeliveryError
from ikea_sniper.scraper import ScrapedProduct
from ikea_sniper.search import ProductSearchResult
from ikea_sniper.telegram import TelegramClient, format_match_message


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def read(self) -> bytes:
        return json.dumps({"ok": True}).encode("utf-8")


def test_format_match_message_contains_required_fields():
    product = ScrapedProduct(
        product_id="1",
        title="HOPPVALS",
        price="14.99€",
        link="https://example.test/product",
        list_text="",
        detail_text="",
        search_text="",
    )
    match = ProductSearchResult(product, ("jalousie",))

    message = format_match_message(match)

    assert "Titel: HOPPVALS" in message
    assert "Preis: 14.99€" in message
    assert "Link: https://example.test/product" in message
    assert "Suchworte: jalousie" in message


def test_telegram_client_posts_to_send_message(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["data"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(telegram.request, "urlopen", fake_urlopen)

    TelegramClient("TOKEN", "CHAT").send_message("Hallo")

    assert captured["url"].endswith("/botTOKEN/sendMessage")
    assert "chat_id=CHAT" in captured["data"]
    assert "text=Hallo" in captured["data"]
    assert captured["timeout"] == telegram.TELEGRAM_TIMEOUT_SECONDS


def test_telegram_client_raises_delivery_error_on_url_error(monkeypatch):
    def fake_urlopen(_request, timeout):
        raise URLError("offline")

    monkeypatch.setattr(telegram.request, "urlopen", fake_urlopen)

    with pytest.raises(TelegramDeliveryError):
        TelegramClient("TOKEN", "CHAT").send_message("Hallo")


def test_telegram_client_includes_http_error_description(monkeypatch):
    def fake_urlopen(_request, timeout):
        response_body = json.dumps(
            {
                "ok": False,
                "description": "Bad Request: chat not found",
            }
        ).encode("utf-8")
        raise HTTPError(
            url="https://api.telegram.org/botTOKEN/sendMessage",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=BytesIO(response_body),
        )

    monkeypatch.setattr(telegram.request, "urlopen", fake_urlopen)

    with pytest.raises(TelegramDeliveryError) as error:
        TelegramClient("TOKEN", "CHAT").send_message("Hallo")

    assert "HTTP 400" in str(error.value)
    assert "Bad Request: chat not found" in str(error.value)
