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
        self.send_message(format_match_message(match))

    def send_error_report(self, report: ErrorReport) -> None:
        self.send_message(format_error_report(report))

    def send_message(self, text: str) -> None:
        payload = parse.urlencode(
            {
                "chat_id": self._chat_id,
                "text": _limit_message(text),
                "disable_web_page_preview": "false",
            }
        ).encode("utf-8")
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
                f"Telegram API antwortete mit HTTP {exception.code}: {description}"
            ) from exception
        except error.URLError as exception:
            raise TelegramDeliveryError(
                f"Telegram API ist nicht erreichbar: {exception.reason}"
            ) from exception
        except TimeoutError as exception:
            raise TelegramDeliveryError(
                "Telegram API hat nicht rechtzeitig geantwortet."
            ) from exception
        except json.JSONDecodeError as exception:
            raise TelegramDeliveryError(
                "Telegram API lieferte keine gueltige JSON-Antwort."
            ) from exception

        if not response_payload.get("ok"):
            description = response_payload.get("description", "Unbekannter Fehler")
            raise TelegramDeliveryError(
                f"Telegram API meldete einen Fehler: {description}"
            )


def format_match_message(match: ProductSearchResult) -> str:
    return "\n".join(
        [
            "Neuer IKEA Second-Hand Treffer",
            "",
            f"Titel: {match.product.title}",
            f"Preis: {match.product.price}",
            f"Link: {match.product.link}",
            f"Suchworte: {', '.join(match.matched_terms)}",
        ]
    )


def format_error_report(report: ErrorReport) -> str:
    return "\n".join(
        [
            "Fehler im IKEA Sniper",
            "",
            f"Art: {report.error_type}",
            f"Komponente: {report.component.value}",
            f"Zeitpunkt: {report.occurred_at.isoformat(timespec='seconds')}",
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
