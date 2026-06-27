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
                "SEARCH_TERMS=Bett, sofa ,TISCH",
                "CHECK_INTERVAL_SECONDS=120",
                "TELEGRAM_BOT_TOKEN=token",
                "TELEGRAM_CHAT_ID=chat",
            ]
        ),
    )

    config = load_config(tmp_path)

    assert config.location == "kassel"
    assert config.search_terms == ("bett", "sofa", "tisch")
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
                "SEARCH_TERMS=bett",
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
                "SEARCH_TERMS=bett",
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
    assert "LOCATION muss gesetzt sein." in message
    assert "SEARCH_TERMS muss mindestens ein Suchwort enthalten." in message
    assert "TELEGRAM_BOT_TOKEN muss gesetzt sein." in message
    assert "TELEGRAM_CHAT_ID muss gesetzt sein." in message
    assert "CHECK_INTERVAL_SECONDS muss groesser als 0 sein." in message


def test_load_config_rejects_invalid_product_detail_scraping_value(tmp_path):
    write_env(
        tmp_path,
        "\n".join(
            [
                "LOCATION=kassel",
                "SEARCH_TERMS=bett",
                "SCRAPE_PRODUCT_DETAILS=maybe",
                "TELEGRAM_BOT_TOKEN=token",
                "TELEGRAM_CHAT_ID=chat",
            ]
        ),
    )

    with pytest.raises(ConfigError) as error:
        load_config(tmp_path)

    assert "SCRAPE_PRODUCT_DETAILS muss true oder false sein." in str(error.value)


def test_process_environment_overrides_dotenv_values(tmp_path, monkeypatch):
    write_env(
        tmp_path,
        "\n".join(
            [
                "LOCATION=kassel",
                "SEARCH_TERMS=bett",
                "CHECK_INTERVAL_SECONDS=300",
                "TELEGRAM_BOT_TOKEN=env-file-token",
                "TELEGRAM_CHAT_ID=env-file-chat",
            ]
        ),
    )
    monkeypatch.setenv("LOCATION", "hamburg")
    monkeypatch.setenv("SEARCH_TERMS", "stuhl,regal")
    monkeypatch.setenv("CHECK_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("SCRAPE_PRODUCT_DETAILS", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "process-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "process-chat")

    config = load_config(tmp_path)

    assert config.location == "hamburg"
    assert config.search_terms == ("stuhl", "regal")
    assert config.check_interval_seconds == 60
    assert config.scrape_product_details is False
    assert config.telegram_bot_token == "process-token"
    assert config.telegram_chat_id == "process-chat"
