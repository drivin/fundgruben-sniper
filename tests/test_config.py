from __future__ import annotations

import pytest

from ikea_sniper.config import ConfigError, load_config


@pytest.fixture(autouse=True)
def clear_config_environment(monkeypatch):
    for key in (
        "LOCATION",
        "SEARCH_TERMS",
        "CHECK_INTERVAL_SECONDS",
        "SCRAPE_PRODUCT_DETAILS",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ):
        monkeypatch.delenv(key, raising=False)


def write_env(project_root, content: str) -> None:
    (project_root / ".env").write_text(content, encoding="utf-8")


def test_load_config_reads_and_normalizes_values(tmp_path):
    write_env(
        tmp_path,
        "\n".join(
            [
                "LOCATION=kassel",
                "SEARCH_TERMS=Bed, sofa ,TABLE",
                "CHECK_INTERVAL_SECONDS=120",
                "TELEGRAM_BOT_TOKEN=token",
                "TELEGRAM_CHAT_ID=chat",
            ]
        ),
    )

    config = load_config(tmp_path)

    assert config.location == "kassel"
    assert config.search_terms == ("bed", "sofa", "table")
    assert config.check_interval_seconds == 120
    assert config.scrape_product_details is True
    assert config.telegram_bot_token == "token"
    assert config.telegram_chat_id == "chat"
    assert (
        config.target_url
        == "https://www.ikea.com/de/de/second-hand/buy-from-ikea/#/kassel"
    )


def test_load_config_uses_default_check_interval(tmp_path):
    write_env(
        tmp_path,
        "\n".join(
            [
                "LOCATION=kassel",
                "SEARCH_TERMS=bed",
                "TELEGRAM_BOT_TOKEN=token",
                "TELEGRAM_CHAT_ID=chat",
            ]
        ),
    )

    assert load_config(tmp_path).check_interval_seconds == 300


def test_load_config_can_disable_product_detail_scraping(tmp_path):
    write_env(
        tmp_path,
        "\n".join(
            [
                "LOCATION=kassel",
                "SEARCH_TERMS=bed",
                "SCRAPE_PRODUCT_DETAILS=false",
                "TELEGRAM_BOT_TOKEN=token",
                "TELEGRAM_CHAT_ID=chat",
            ]
        ),
    )

    assert load_config(tmp_path).scrape_product_details is False


def test_load_config_rejects_missing_required_values(tmp_path):
    write_env(tmp_path, "CHECK_INTERVAL_SECONDS=0")

    with pytest.raises(ConfigError) as error:
        load_config(tmp_path)

    message = str(error.value)
    assert "LOCATION must be set." in message
    assert "SEARCH_TERMS must contain at least one search term." in message
    assert "TELEGRAM_BOT_TOKEN must be set." in message
    assert "TELEGRAM_CHAT_ID must be set." in message
    assert "CHECK_INTERVAL_SECONDS must be greater than 0." in message


def test_load_config_rejects_invalid_product_detail_scraping_value(tmp_path):
    write_env(
        tmp_path,
        "\n".join(
            [
                "LOCATION=kassel",
                "SEARCH_TERMS=bed",
                "SCRAPE_PRODUCT_DETAILS=maybe",
                "TELEGRAM_BOT_TOKEN=token",
                "TELEGRAM_CHAT_ID=chat",
            ]
        ),
    )

    with pytest.raises(ConfigError) as error:
        load_config(tmp_path)

    assert "SCRAPE_PRODUCT_DETAILS must be true or false." in str(error.value)


def test_process_environment_overrides_dotenv_values(tmp_path, monkeypatch):
    write_env(
        tmp_path,
        "\n".join(
            [
                "LOCATION=kassel",
                "SEARCH_TERMS=bed",
                "CHECK_INTERVAL_SECONDS=300",
                "TELEGRAM_BOT_TOKEN=env-file-token",
                "TELEGRAM_CHAT_ID=env-file-chat",
            ]
        ),
    )
    monkeypatch.setenv("LOCATION", "hamburg")
    monkeypatch.setenv("SEARCH_TERMS", "chair,shelf")
    monkeypatch.setenv("CHECK_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("SCRAPE_PRODUCT_DETAILS", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "process-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "process-chat")

    config = load_config(tmp_path)

    assert config.location == "hamburg"
    assert config.search_terms == ("chair", "shelf")
    assert config.check_interval_seconds == 60
    assert config.scrape_product_details is False
    assert config.telegram_bot_token == "process-token"
    assert config.telegram_chat_id == "process-chat"
