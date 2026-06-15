from __future__ import annotations

import logging
import signal
import threading
from pathlib import Path

from ikea_sniper.config import AppConfig, ConfigError, load_config
from ikea_sniper.errors import ErrorComponent, RunErrorReporter
from ikea_sniper.logging_config import configure_logging
from ikea_sniper.scraper import scrape_products_with_details
from ikea_sniper.search import find_matching_products
from ikea_sniper.status import ProductStatusStore, filter_new_matches
from ikea_sniper.telegram import TelegramClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
STATUS_DIR = DATA_DIR / "status"
LOG_DIR = DATA_DIR / "logs"
LOGGER = logging.getLogger(__name__)


def ensure_local_data_directories() -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def install_shutdown_handlers(shutdown_event: threading.Event) -> None:
    def handle_shutdown_signal(signum: int, _frame: object) -> None:
        LOGGER.info("Shutdown signal received: %s", signum)
        shutdown_event.set()

    for signal_name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        if hasattr(signal, signal_name):
            signal.signal(getattr(signal, signal_name), handle_shutdown_signal)


def main() -> None:
    ensure_local_data_directories()
    log_file = configure_logging(LOG_DIR)
    LOGGER.info("Application starting.")
    LOGGER.info("Persistent log file: %s", log_file)

    try:
        config = load_config(PROJECT_ROOT)
    except ConfigError as error:
        LOGGER.error("Configuration error: %s", error)
        raise SystemExit(str(error)) from error

    LOGGER.info("IKEA Sniper configuration is valid.")
    LOGGER.info("Status directory: %s", STATUS_DIR)
    LOGGER.info("Log directory: %s", LOG_DIR)
    LOGGER.info("Location: %s", config.location)
    LOGGER.info("Search terms: %s", ", ".join(config.search_terms))
    LOGGER.info("Check interval seconds: %s", config.check_interval_seconds)
    LOGGER.info("Target URL: %s", config.target_url)

    telegram_client = TelegramClient(
        config.telegram_bot_token,
        config.telegram_chat_id,
    )
    shutdown_event = threading.Event()
    install_shutdown_handlers(shutdown_event)
    run_scheduler(config, telegram_client, shutdown_event)


def run_scheduler(
    config: AppConfig,
    telegram_client: TelegramClient,
    shutdown_event: threading.Event,
) -> None:
    LOGGER.info("Scheduler started. First check runs immediately.")
    while not shutdown_event.is_set():
        run_check(config, telegram_client)

        if shutdown_event.is_set():
            break

        LOGGER.info(
            "Next check starts in %s seconds.",
            config.check_interval_seconds,
        )
        shutdown_event.wait(config.check_interval_seconds)

    LOGGER.info("Application stopped.")


def run_check(config: AppConfig, telegram_client: TelegramClient) -> None:
    LOGGER.info("Check run started.")
    reporter = RunErrorReporter(LOGGER, telegram_client.send_error_report)

    try:
        products = scrape_products_with_details(
            config.target_url,
            config.location,
            LOGGER,
        )
    except Exception as error:
        reporter.report(error, ErrorComponent.SCRAPING)
        LOGGER.info("Check run finished with scraping error.")
        return

    LOGGER.info("Found %s products.", len(products))
    for product in products:
        LOGGER.info(
            "Product: id=%s title=%s price=%s link=%s detail_text=%s search_text=%s",
            product.product_id,
            product.title,
            product.price,
            product.link,
            "yes" if product.detail_text else "no",
            "yes" if product.search_text else "no",
        )

    try:
        status_store = ProductStatusStore(STATUS_DIR)
        status = status_store.load()
        current_product_ids = {product.product_id for product in products}

        matches = find_matching_products(products, config.search_terms)
        duplicate_filter_result = filter_new_matches(
            matches,
            status,
            current_product_ids,
        )
    except Exception as error:
        reporter.report(error, ErrorComponent.SCRAPING)
        LOGGER.info("Check run finished with status error.")
        return

    if duplicate_filter_result.removed_product_ids:
        LOGGER.info(
            "Removed %s disappeared product IDs from status: %s",
            len(duplicate_filter_result.removed_product_ids),
            ", ".join(sorted(duplicate_filter_result.removed_product_ids)),
        )

    LOGGER.info("Found %s matching products.", len(matches))
    LOGGER.info(
        "Found %s new matching products and %s already reported matching products.",
        len(duplicate_filter_result.new_matches),
        len(duplicate_filter_result.already_reported_matches),
    )

    for match in duplicate_filter_result.new_matches:
        LOGGER.info(
            "New matching product: id=%s title=%s price=%s terms=%s link=%s",
            match.product.product_id,
            match.product.title,
            match.product.price,
            ", ".join(match.matched_terms),
            match.product.link,
        )
        try:
            telegram_client.send_match(match)
        except Exception as error:
            reporter.report(error, ErrorComponent.TELEGRAM_DELIVERY)
        else:
            status.mark_reported({match.product.product_id})
            LOGGER.info(
                "Telegram match notification sent: id=%s",
                match.product.product_id,
            )

    for match in duplicate_filter_result.already_reported_matches:
        LOGGER.info(
            "Already reported matching product skipped: "
            "id=%s title=%s price=%s terms=%s link=%s",
            match.product.product_id,
            match.product.title,
            match.product.price,
            ", ".join(match.matched_terms),
            match.product.link,
        )

    try:
        status_store.save(status)
    except Exception as error:
        reporter.report(error, ErrorComponent.SCRAPING)
        LOGGER.info("Check run finished with status save error.")
        return

    LOGGER.info("Check run finished.")


if __name__ == "__main__":
    main()
