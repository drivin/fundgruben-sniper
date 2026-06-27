from __future__ import annotations

import re
from dataclasses import dataclass
from logging import Logger
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from ikea_sniper.errors import IkeaFetchError, ScrapingError


PRODUCT_ID_PATTERN = re.compile(r"#/[^/]+/(?P<product_id>\d+)(?:$|[/?#])")
SCRAPE_TIMEOUT_MS = 30_000
NETWORK_IDLE_TIMEOUT_MS = 10_000
DETAIL_READY_TIMEOUT_MS = 10_000
IKEA_SECOND_HAND_PAGE_URL = "https://www.ikea.com/de/de/second-hand/buy-from-ikea/"
BLOCKED_RESOURCE_TYPES = {"font", "image", "media", "stylesheet"}
BROWSER_LAUNCH_ARGS = (
    "--blink-settings=imagesEnabled=false",
    "--disable-background-networking",
    "--disable-dev-shm-usage",
    "--disable-gpu",
)


@dataclass(frozen=True)
class ProductListItem:
    product_id: str
    title: str
    price: str
    link: str
    list_text: str = ""


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
            browser = playwright.chromium.launch(
                headless=True,
                args=list(BROWSER_LAUNCH_ARGS),
            )
            try:
                page = _new_optimized_page(browser)
                _open_page(page, target_url, PlaywrightTimeoutError)
                return _extract_items_from_page(page, location, target_url)
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
    *,
    scrape_product_details: bool = True,
) -> list[ScrapedProduct]:
    playwright_api = _load_playwright_api()
    sync_playwright = playwright_api["sync_playwright"]
    PlaywrightError = playwright_api["PlaywrightError"]
    PlaywrightTimeoutError = playwright_api["PlaywrightTimeoutError"]

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=list(BROWSER_LAUNCH_ARGS),
            )
            try:
                page = _new_optimized_page(browser)
                _open_page(page, target_url, PlaywrightTimeoutError)
                list_items = _extract_items_from_page(page, location, target_url)

                if not scrape_product_details:
                    return [_product_from_list_item(item) for item in list_items]

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


def _new_optimized_page(browser: Any) -> Any:
    context = browser.new_context(
        device_scale_factor=1,
        reduced_motion="reduce",
        viewport={"width": 1280, "height": 720},
    )
    page = context.new_page()
    page.route("**/*", _route_request)
    return page


def _route_request(route: Any) -> None:
    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
        route.abort()
        return

    route.continue_()


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


def _extract_items_from_page(
    page: Any,
    location: str,
    target_url: str,
) -> list[ProductListItem]:
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

    api_items = _extract_items_from_grouped_search_api(page, location, target_url)
    if api_items:
        return api_items

    return _extract_items_from_dom(page, location)


def _extract_items_from_grouped_search_api(
    page: Any,
    location: str,
    target_url: str,
) -> list[ProductListItem]:
    search_url = _find_grouped_search_url(page)
    if not search_url:
        return []

    try:
        first_payload = _get_json(page, _build_api_page_url(search_url, 0))
        total_pages = int(first_payload.get("totalPages", 1))
        items = _items_from_grouped_search_payload(
            first_payload,
            location,
            target_url,
        )

        for page_number in range(1, total_pages):
            payload = _get_json(page, _build_api_page_url(search_url, page_number))
            items.extend(
                _items_from_grouped_search_payload(
                    payload,
                    location,
                    target_url,
                )
            )

        return _deduplicate_items(items)
    except Exception:
        return []


def _find_grouped_search_url(page: Any) -> str:
    return str(
        page.evaluate(
            """
            () => performance
                .getEntriesByType('resource')
                .map((entry) => entry.name)
                .find((url) => url.includes('/circular/circular-asis/offers/grouped/search?'))
                || ''
            """
        )
    )


def _get_json(page: Any, url: str) -> dict[str, Any]:
    response = page.request.get(url)
    if not response.ok:
        raise ScrapingError(f"IKEA-API antwortete mit HTTP {response.status}: {url}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ScrapingError(f"IKEA-API lieferte kein JSON-Objekt: {url}")
    return payload


def _build_api_page_url(search_url: str, page_number: int) -> str:
    parsed_url = urlparse(search_url)
    query = parse_qs(parsed_url.query)
    query["page"] = [str(page_number)]
    return urlunparse(
        parsed_url._replace(
            query=urlencode(query, doseq=True),
        )
    )


def _items_from_grouped_search_payload(
    payload: dict[str, Any],
    location: str,
    target_url: str,
) -> list[ProductListItem]:
    content = payload.get("content")
    if not isinstance(content, list):
        return []

    items = []
    for group in content:
        if not isinstance(group, dict):
            continue

        product_id = _first_offer_number(group)
        title = _normalize_text(str(group.get("title", "")))
        price = _format_group_price(group)
        link = _build_product_link(target_url, location, product_id)
        list_text = _api_group_search_text(group, price, link)

        item = {
            "title": title,
            "price": price,
            "link": link,
        }
        if not product_id or not _has_required_fields(item):
            continue

        items.append(
            ProductListItem(
                product_id=product_id,
                title=title,
                price=price,
                link=link,
                list_text=list_text,
            )
        )

    return items


def _first_offer_number(group: dict[str, Any]) -> str:
    offers = group.get("offers")
    if not isinstance(offers, list):
        return ""

    for offer in offers:
        if not isinstance(offer, dict):
            continue
        offer_number = str(offer.get("offerNumber", "")).strip()
        if offer_number:
            return offer_number

    return ""


def _format_group_price(group: dict[str, Any]) -> str:
    currency = str(group.get("currency", "EUR")).strip() or "EUR"
    min_price = _number_or_none(group.get("minPrice"))
    max_price = _number_or_none(group.get("maxPrice"))

    if min_price is None:
        min_price = _first_offer_price(group)
    if max_price is None:
        max_price = min_price

    if min_price is None:
        return ""

    formatted_min = _format_price(min_price, currency)
    if max_price is None or min_price == max_price:
        return formatted_min

    return f"{formatted_min} - {_format_price(max_price, currency)}"


def _first_offer_price(group: dict[str, Any]) -> float | None:
    offers = group.get("offers")
    if not isinstance(offers, list):
        return None

    for offer in offers:
        if not isinstance(offer, dict):
            continue
        price = _number_or_none(offer.get("price"))
        if price is not None:
            return price

    return None


def _number_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _format_price(value: float, currency: str) -> str:
    suffix = "€" if currency == "EUR" else f" {currency}"
    return f"{value:.2f}{suffix}"


def _build_product_link(target_url: str, location: str, product_id: str) -> str:
    parsed_url = urlparse(target_url)
    if parsed_url.scheme and parsed_url.netloc:
        base_url = urlunparse(parsed_url._replace(fragment="", query=""))
    else:
        base_url = IKEA_SECOND_HAND_PAGE_URL
    return f"{base_url}#/{location}/{product_id}"


def _api_group_search_text(group: dict[str, Any], price: str, link: str) -> str:
    parts = [
        str(group.get("title", "")),
        str(group.get("description", "")),
        price,
        link,
        " ".join(str(article) for article in group.get("articleNumbers", []) or []),
    ]

    offers = group.get("offers")
    if isinstance(offers, list):
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            parts.extend(
                str(offer.get(key, ""))
                for key in (
                    "description",
                    "additionalInfo",
                    "productConditionTitle",
                    "productConditionDescription",
                    "reasonDiscount",
                )
            )

    return _combine_text_parts(*parts)


def _deduplicate_items(items: list[ProductListItem]) -> list[ProductListItem]:
    seen = set()
    deduplicated = []
    for item in items:
        if item.product_id in seen:
            continue
        seen.add(item.product_id)
        deduplicated.append(item)
    return deduplicated


def _extract_items_from_dom(page: Any, location: str) -> list[ProductListItem]:
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
                list_text=_combine_text_parts(
                    str(item["title"]).strip(),
                    str(item["price"]).strip(),
                    link,
                ),
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
    list_text = item.list_text or _combine_text_parts(item.title, item.price, item.link)
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


def _product_from_list_item(item: ProductListItem) -> ScrapedProduct:
    list_text = item.list_text or _combine_text_parts(item.title, item.price, item.link)
    return ScrapedProduct(
        product_id=item.product_id,
        title=item.title,
        price=item.price,
        link=item.link,
        list_text=list_text,
        detail_text="",
        search_text=list_text,
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
