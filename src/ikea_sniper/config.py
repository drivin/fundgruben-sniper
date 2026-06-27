from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


DEFAULT_CHECK_INTERVAL_SECONDS = 300
IKEA_SECOND_HAND_BASE_URL = "https://www.ikea.com/de/de/second-hand/buy-from-ikea/#"


@dataclass(frozen=True)
class AppConfig:
    location: str
    search_terms: tuple[str, ...]
    check_interval_seconds: int
    scrape_product_details: bool
    telegram_bot_token: str
    telegram_chat_id: str
    target_url: str


class ConfigError(ValueError):
    pass


def load_config(project_root: Path) -> AppConfig:
    values = _read_env(project_root / ".env")
    values.update(_read_process_env())
    errors: list[str] = []

    location = _required_value(values, "LOCATION", errors)
    search_terms = _parse_search_terms(values.get("SEARCH_TERMS", ""), errors)
    check_interval_seconds = _parse_check_interval(
        values.get("CHECK_INTERVAL_SECONDS", ""),
        errors,
    )
    scrape_product_details = _parse_bool(
        values.get("SCRAPE_PRODUCT_DETAILS", ""),
        default=True,
        key="SCRAPE_PRODUCT_DETAILS",
        errors=errors,
    )
    telegram_bot_token = _required_value(values, "TELEGRAM_BOT_TOKEN", errors)
    telegram_chat_id = _required_value(values, "TELEGRAM_CHAT_ID", errors)

    if errors:
        raise ConfigError("Invalid configuration:\n- " + "\n- ".join(errors))

    return AppConfig(
        location=location,
        search_terms=search_terms,
        check_interval_seconds=check_interval_seconds,
        scrape_product_details=scrape_product_details,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        target_url=f"{IKEA_SECOND_HAND_BASE_URL}/{location}",
    )


def _read_env(env_path: Path) -> dict[str, str]:
    return {key: value or "" for key, value in dotenv_values(env_path).items()}


def _read_process_env() -> dict[str, str]:
    keys = (
        "LOCATION",
        "SEARCH_TERMS",
        "CHECK_INTERVAL_SECONDS",
        "SCRAPE_PRODUCT_DETAILS",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    )
    return {
        key: os.environ[key]
        for key in keys
        if key in os.environ
    }


def _required_value(values: dict[str, str], key: str, errors: list[str]) -> str:
    value = values.get(key, "").strip()
    if not value:
        errors.append(f"{key} must be set.")
    return value


def _parse_search_terms(raw_value: str, errors: list[str]) -> tuple[str, ...]:
    terms = tuple(
        term.strip().casefold()
        for term in raw_value.split(",")
        if term.strip()
    )
    if not terms:
        errors.append("SEARCH_TERMS must contain at least one search term.")
    return terms


def _parse_check_interval(raw_value: str, errors: list[str]) -> int:
    value = raw_value.strip()
    if not value:
        return DEFAULT_CHECK_INTERVAL_SECONDS

    try:
        check_interval_seconds = int(value)
    except ValueError:
        errors.append("CHECK_INTERVAL_SECONDS must be an integer.")
        return DEFAULT_CHECK_INTERVAL_SECONDS

    if check_interval_seconds <= 0:
        errors.append("CHECK_INTERVAL_SECONDS must be greater than 0.")
        return DEFAULT_CHECK_INTERVAL_SECONDS

    return check_interval_seconds


def _parse_bool(
    raw_value: str,
    *,
    default: bool,
    key: str,
    errors: list[str],
) -> bool:
    value = raw_value.strip().casefold()
    if not value:
        return default

    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False

    errors.append(f"{key} must be true or false.")
    return default
