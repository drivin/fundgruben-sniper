FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && python -m playwright install --with-deps chromium

RUN mkdir -p /app/data/status /app/data/logs

CMD ["python", "-m", "ikea_sniper"]
