from __future__ import annotations

import re
from dataclasses import dataclass
from logging import Logger
from typing import Any

from ikea_sniper.errors import IkeaFetchError, ScrapingError


PRODUCT_ID_PATTERN = re.compile(r"#/[^/]+/(?P<product_id>\d+)(?:$|[/?#])")
SCRAPE_TIMEOUT_MS = 30_000
NETWORK_IDLE_TIMEOUT_MS = 10_000
DETAIL_READY_TIMEOUT_MS = 10_000


@dataclass(frozen=True)
class ProductListItem:
    product_id: str
    title: str
    price: str
    link: str


@dataclass(frozen=True)
class ScrapedProduct:
    product_id: str
    title: str
    price: str
    link: str
    list_text: str
    detail_text: str
    search_text: str
    detail_error: str | None = None


def extract_product_id(link: str) -> str:
    match = PRODUCT_ID_PATTERN.search(link)
    if match is None:
        raise ScrapingError(f"Produkt-ID konnte nicht aus Link gelesen werden: {link}")
    return match.group("product_id")


def scrape_product_list(target_url: str, location: str) -> list[ProductListItem]:
    playwright_api = _load_playwright_api()
    sync_playwright = playwright_api["sync_playwright"]
    PlaywrightError = playwright_api["PlaywrightError"]
    PlaywrightTimeoutError = playwright_api["PlaywrightTimeoutError"]

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                _open_page(page, target_url, PlaywrightTimeoutError)
                return _extract_items_from_page(page, location)
            finally:
                browser.close()
    except ScrapingError:
        raise
    except PlaywrightTimeoutError as error:
        raise IkeaFetchError(
            f"IKEA-Seite konnte nicht rechtzeitig geladen werden: {target_url}"
        ) from error
    except PlaywrightError as error:
        raise IkeaFetchError(f"IKEA-Abruf ist fehlgeschlagen: {error}") from error


def scrape_products_with_details(
    target_url: str,
    location: str,
    logger: Logger,
) -> list[ScrapedProduct]:
    playwright_api = _load_playwright_api()
    sync_playwright = playwright_api["sync_playwright"]
    PlaywrightError = playwright_api["PlaywrightError"]
    PlaywrightTimeoutError = playwright_api["PlaywrightTimeoutError"]

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                _open_page(page, target_url, PlaywrightTimeoutError)
                list_items = _extract_items_from_page(page, location)

                products = []
                for item in list_items:
                    products.append(
                        _scrape_product_detail(
                            page,
                            item,
                            logger,
                            PlaywrightTimeoutError,
                        )
                    )
                return products
            finally:
                browser.close()
    except ScrapingError:
        raise
    except PlaywrightTimeoutError as error:
        raise IkeaFetchError(
            f"IKEA-Seite konnte nicht rechtzeitig geladen werden: {target_url}"
        ) from error
    except PlaywrightError as error:
        raise IkeaFetchError(f"IKEA-Abruf ist fehlgeschlagen: {error}") from error


def _load_playwright_api() -> dict[str, Any]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise IkeaFetchError(
            "Playwright ist nicht installiert. Fuehre `python -m pip install -e .` aus."
        ) from error

    return {
        "sync_playwright": sync_playwright,
        "PlaywrightError": PlaywrightError,
        "PlaywrightTimeoutError": PlaywrightTimeoutError,
    }


def _open_page(page: Any, url: str, playwright_timeout_error: type[Exception]) -> None:
    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=SCRAPE_TIMEOUT_MS,
    )
    try:
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
    except playwright_timeout_error:
        pass


def _extract_items_from_page(page: Any, location: str) -> list[ProductListItem]:
    try:
        page.wait_for_function(
            """
            (location) => Array
                .from(document.querySelectorAll('a[href*="#/"]'))
                .some((anchor) => anchor.href.includes(`#/${location}/`))
            """,
            arg=location,
            timeout=SCRAPE_TIMEOUT_MS,
        )
    except Exception as error:
        raise ScrapingError(
            "Keine erwartbaren Artikellinks in der IKEA-Listenansicht gefunden."
        ) from error

    raw_items = page.locator('a[href*="#/"]').evaluate_all(
        """
        (anchors, location) => {
            const locationPath = `#/${location}/`;
            const seen = new Set();

            function normalizeText(value) {
                return (value || '').replace(/\\s+/g, ' ').trim();
            }

            function nearestCard(anchor) {
                let current = anchor;
                for (let depth = 0; depth < 8 && current; depth += 1) {
                    const text = normalizeText(current.innerText || current.textContent || '');
                    if (text.includes('€') && text.length <= 2000) {
                        return current;
                    }
                    current = current.parentElement;
                }
                return anchor;
            }

            function findPrice(card, text) {
                const priceNodes = Array
                    .from(card.querySelectorAll('[data-skapa^="price"], .price'))
                    .filter((node) => !String(node.className).includes('price--comparison'));

                for (const node of priceNodes) {
                    const match = (node.innerText || node.textContent || '').match(
                        /(?:€[\\s\\u00a0]*)?(?:\\d+[,.]\\d{2}|\\d+)[\\s\\u00a0]*(?:€|,-|\\.\\-)/
                    );
                    if (match) {
                        return normalizeText(match[0]);
                    }
                }

                const match = text.match(
                    /(?:€[\\s\\u00a0]*)?(?:\\d+[,.]\\d{2}|\\d+)[\\s\\u00a0]*(?:€|,-|\\.\\-)/
                );
                return match ? normalizeText(match[0]) : '';
            }

            function findTitle(anchor, cardText, price) {
                const anchorLines = (anchor.innerText || '')
                    .split('\\n')
                    .map(normalizeText)
                    .filter(Boolean);
                const cardLines = cardText
                    .split('\\n')
                    .map(normalizeText)
                    .filter(Boolean);
                const lines = [...anchorLines, ...cardLines];

                for (const line of lines) {
                    if (
                        line === price ||
                        line.includes('€') ||
                        /^-\\d+%$/.test(line) ||
                        line.toLowerCase().includes('preis')
                    ) {
                        continue;
                    }
                    return line;
                }

                return '';
            }

            return anchors.flatMap((anchor) => {
                const link = anchor.href;
                if (!link.includes(locationPath) || seen.has(link)) {
                    return [];
                }

                seen.add(link);
                const card = nearestCard(anchor);
                const cardText = card.innerText || card.textContent || '';
                const price = findPrice(card, cardText);
                const title = findTitle(anchor, cardText, price);

                return [{
                    title,
                    price,
                    link,
                }];
            });
        }
        """,
        location,
    )

    items = []
    for item in raw_items:
        if not _has_required_fields(item):
            continue

        link = str(item["link"]).strip()
        try:
            product_id = extract_product_id(link)
        except ScrapingError:
            continue

        items.append(
            ProductListItem(
                product_id=product_id,
                title=str(item["title"]).strip(),
                price=str(item["price"]).strip(),
                link=link,
            )
        )

    if not items:
        raise ScrapingError(
            "Artikellinks wurden gefunden, aber Titel, Preis oder Produkt-ID konnten "
            "nicht vollstaendig extrahiert werden."
        )

    return items


def _scrape_product_detail(
    page: Any,
    item: ProductListItem,
    logger: Logger,
    playwright_timeout_error: type[Exception],
) -> ScrapedProduct:
    list_text = _combine_text_parts(item.title, item.price, item.link)
    detail_text = ""
    detail_error = None

    try:
        _open_page(page, item.link, playwright_timeout_error)
        try:
            page.wait_for_function(
                """
                (title) => document.body
                    && document.body.innerText
                    && document.body.innerText.toLowerCase().includes(title.toLowerCase())
                """,
                arg=item.title,
                timeout=DETAIL_READY_TIMEOUT_MS,
            )
        except playwright_timeout_error:
            pass

        detail_text = _extract_visible_text(page)
        if not detail_text:
            raise ScrapingError(
                f"Detailseite enthaelt keinen sichtbaren Text: {item.link}"
            )
    except Exception as error:
        detail_error = str(error)
        logger.warning(
            "Detail page scraping failed for product_id=%s link=%s: %s",
            item.product_id,
            item.link,
            error,
            exc_info=True,
        )

    return ScrapedProduct(
        product_id=item.product_id,
        title=item.title,
        price=item.price,
        link=item.link,
        list_text=list_text,
        detail_text=detail_text,
        search_text=_combine_text_parts(list_text, detail_text),
        detail_error=detail_error,
    )


def _extract_visible_text(page: Any) -> str:
    for selector in ("main", "[role='main']", "body"):
        locator = page.locator(selector).first
        try:
            if locator.count() > 0:
                text = locator.inner_text(timeout=SCRAPE_TIMEOUT_MS)
                normalized_text = _normalize_text(text)
                if normalized_text:
                    return normalized_text
        except Exception:
            continue

    return ""


def _combine_text_parts(*parts: str) -> str:
    return _normalize_text(" ".join(part for part in parts if part))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _has_required_fields(item: dict[str, object]) -> bool:
    return all(
        str(item.get(field, "")).strip()
        for field in ("title", "price", "link")
    )
