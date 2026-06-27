# Fundgruben Sniper

Fundgruben Sniper watches an IKEA Second-Hand location page and sends Telegram notifications when matching items appear.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by IKEA. IKEA is a trademark of Inter IKEA Systems B.V. Use this tool responsibly and respect IKEA's website terms and robots policies.

## Features

- Playwright-based IKEA Second-Hand scraping
- Product detail scraping for broader search coverage
- Case-insensitive substring matching
- Telegram notifications for new matches
- Rate-limited Telegram error reports
- Persistent duplicate tracking
- Docker Compose support
- GitHub Actions Docker image publishing

## Requirements

- Linux
- Python 3.11+
- Docker and Docker Compose, for container usage
- Telegram bot token and chat ID

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
cp .env.example .env
```

Edit `.env`:

```env
LOCATION=kassel
SEARCH_TERMS=bett,sofa,tisch
CHECK_INTERVAL_SECONDS=300
SCRAPE_PRODUCT_DETAILS=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

`LOCATION` is used to build:

```text
https://www.ikea.com/de/de/second-hand/buy-from-ikea/#/{LOCATION}
```

## Usage

Run locally:

```bash
source .venv/bin/activate
python -m ikea_sniper
```

Or use the installed command:

```bash
ikea-sniper
```

Run with Docker Compose:

```bash
cp .env.example .env
docker compose up --build
```

Background mode:

```bash
docker compose up -d --build
```

Logs:

```bash
docker compose logs -f ikea-sniper
```

Stop:

```bash
docker compose down
```

## Configuration

- `LOCATION`: IKEA Second-Hand location slug, for example `kassel`
- `SEARCH_TERMS`: comma-separated search terms
- `CHECK_INTERVAL_SECONDS`: polling interval in seconds, defaults to `300`
- `SCRAPE_PRODUCT_DETAILS`: set to `false` to avoid opening every product detail
  page. This significantly reduces browser CPU usage, but searches only list/API
  text and can miss terms that appear exclusively on detail pages.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token
- `TELEGRAM_CHAT_ID`: Telegram target chat ID

The first check runs immediately on startup. Later checks run every `CHECK_INTERVAL_SECONDS`.

## Persistence

Reported product IDs are stored in:

```text
data/status/reported-products.json
```

Logs are written to:

```text
data/logs/ikea-sniper.log
```

Docker Compose maps both paths to persistent volumes.

## Docker Image

`.github/workflows/docker-image.yml` builds the image with GitHub Actions.

- Pull requests build without publishing.
- Pushes publish to GitHub Container Registry.
- Tags like `v1.2.3` create SemVer image tags.
- The default branch also creates `latest`.

Image name:

```text
ghcr.io/drivin/fundgruben-sniper
```

Published platforms:

- `linux/amd64`
- `linux/arm64`

`linux/arm/v7` is not published because the Playwright Python package used by this project does not provide a compatible distribution for that platform.

## Tests

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

The tests do not call IKEA and do not send Telegram messages.

## Project Structure

```text
.
├── .github/workflows/
├── data/
├── src/ikea_sniper/
├── tests/
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```
