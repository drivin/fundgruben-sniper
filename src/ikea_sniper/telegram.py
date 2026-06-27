from __future__ import annotations

import json
from urllib import error, parse, request

from ikea_sniper.errors import ErrorReport, TelegramDeliveryError
from ikea_sniper.search import ProductSearchResult


TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_TIMEOUT_SECONDS = 15


class TelegramClient:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send_match(self, match: ProductSearchResult) -> None:
        self.send_message(
            format_match_message(match),
            link_preview_url=match.product.image_url or None,
        )

    def send_error_report(self, report: ErrorReport) -> None:
        self.send_message(format_error_report(report))

    def send_message(self, text: str, link_preview_url: str | None = None) -> None:
        payload_values = {
            "chat_id": self._chat_id,
            "text": _limit_message(text),
        }
        if link_preview_url:
            payload_values["link_preview_options"] = json.dumps(
                {
                    "url": link_preview_url,
                }
            )
        else:
            payload_values["disable_web_page_preview"] = "false"

        payload = parse.urlencode(payload_values).encode("utf-8")
        url = f"{TELEGRAM_API_BASE_URL}/bot{self._bot_token}/sendMessage"
        telegram_request = request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        try:
            with request.urlopen(
                telegram_request,
                timeout=TELEGRAM_TIMEOUT_SECONDS,
            ) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exception:
            description = _read_http_error_description(exception)
            raise TelegramDeliveryError(
                f"Telegram API responded with HTTP {exception.code}: {description}"
            ) from exception
        except error.URLError as exception:
            raise TelegramDeliveryError(
                f"Telegram API is not reachable: {exception.reason}"
            ) from exception
        except TimeoutError as exception:
            raise TelegramDeliveryError(
                "Telegram API did not respond in time."
            ) from exception
        except json.JSONDecodeError as exception:
            raise TelegramDeliveryError(
                "Telegram API returned an invalid JSON response."
            ) from exception

        if not response_payload.get("ok"):
            description = response_payload.get("description", "Unknown error")
            raise TelegramDeliveryError(
                f"Telegram API reported an error: {description}"
            )


def format_match_message(match: ProductSearchResult) -> str:
    return "\n".join(
        [
            "New IKEA Second-Hand match",
            "",
            f"Title: {match.product.title}",
            f"Price: {match.product.price}",
            f"Link: {match.product.link}",
            f"Search terms: {', '.join(match.matched_terms)}",
        ]
    )


def format_error_report(report: ErrorReport) -> str:
    return "\n".join(
        [
            "IKEA Sniper error",
            "",
            f"Type: {report.error_type}",
            f"Component: {report.component.value}",
            f"Time: {report.occurred_at.isoformat(timespec='seconds')}",
            f"Details: {report.message}",
        ]
    )


def _limit_message(text: str) -> str:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return text
    return text[: TELEGRAM_MESSAGE_LIMIT - 3] + "..."


def _read_http_error_description(exception: error.HTTPError) -> str:
    try:
        response_body = exception.read().decode("utf-8")
    except Exception:
        return exception.reason or "Bad Request"

    try:
        response_payload = json.loads(response_body)
    except json.JSONDecodeError:
        return response_body or exception.reason or "Bad Request"

    description = response_payload.get("description")
    if description:
        return str(description)

    return response_body or exception.reason or "Bad Request"
