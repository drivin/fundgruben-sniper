from __future__ import annotations

from dataclasses import dataclass

from ikea_sniper.scraper import ScrapedProduct


@dataclass(frozen=True)
class ProductSearchResult:
    product: ScrapedProduct
    matched_terms: tuple[str, ...]


def find_matching_terms(search_text: str, search_terms: tuple[str, ...]) -> tuple[str, ...]:
    normalized_text = search_text.casefold()
    return tuple(
        term
        for term in search_terms
        if term and term.casefold() in normalized_text
    )


def find_matching_products(
    products: list[ScrapedProduct],
    search_terms: tuple[str, ...],
) -> list[ProductSearchResult]:
    matches = []
    for product in products:
        matched_terms = find_matching_terms(product.search_text, search_terms)
        if matched_terms:
            matches.append(
                ProductSearchResult(
                    product=product,
                    matched_terms=matched_terms,
                )
            )

    return matches
