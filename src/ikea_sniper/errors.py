from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from logging import Logger


class ErrorComponent(Enum):
    IKEA_FETCH = "IKEA fetch"
    SCRAPING = "Scraping"
    TELEGRAM_DELIVERY = "Telegram delivery"


@dataclass(frozen=True)
class ErrorReport:
    error_type: str
    component: ErrorComponent
    message: str
    occurred_at: datetime


class AppError(Exception):
    component: ErrorComponent

    def __init__(
        self,
        message: str,
        component: ErrorComponent,
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.component = component
        self.error_type = error_type or self.__class__.__name__


class IkeaFetchError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorComponent.IKEA_FETCH)


class ScrapingError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorComponent.SCRAPING)


class TelegramDeliveryError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorComponent.TELEGRAM_DELIVERY)


TelegramErrorSender = Callable[[ErrorReport], None]


class RunErrorReporter:
    def __init__(
        self,
        logger: Logger,
        telegram_error_sender: TelegramErrorSender | None = None,
    ) -> None:
        self._logger = logger
        self._telegram_error_sender = telegram_error_sender
        self._telegram_error_report_attempted = False

    def report(
        self,
        error: Exception,
        component: ErrorComponent | None = None,
    ) -> ErrorReport:
        report = create_error_report(error, component)
        self._logger.error(
            "%s in %s: %s",
            report.error_type,
            report.component.value,
            report.message,
            exc_info=error,
        )
        self._send_telegram_report_once(report)
        return report

    def _send_telegram_report_once(self, report: ErrorReport) -> None:
        if self._telegram_error_sender is None:
            return

        if report.component is ErrorComponent.TELEGRAM_DELIVERY:
            self._logger.warning(
                "Telegram error report skipped because Telegram delivery failed."
            )
            return

        if self._telegram_error_report_attempted:
            self._logger.warning(
                "Telegram error report skipped because one was already attempted "
                "during this run."
            )
            return

        self._telegram_error_report_attempted = True
        try:
            self._telegram_error_sender(report)
        except Exception as error:
            self._logger.exception(
                "Telegram error report delivery failed: %s",
                error,
            )


def create_error_report(
    error: Exception,
    component: ErrorComponent | None = None,
) -> ErrorReport:
    if isinstance(error, AppError):
        report_component = error.component
        error_type = error.error_type
    elif component is not None:
        report_component = component
        error_type = error.__class__.__name__
    else:
        raise ValueError(
            "component must be set explicitly for generic exceptions."
        )

    return ErrorReport(
        error_type=error_type,
        component=report_component,
        message=str(error),
        occurred_at=datetime.now().astimezone(),
    )
