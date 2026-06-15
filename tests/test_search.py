from __future__ import annotations

from ikea_sniper.scraper import ScrapedProduct
from ikea_sniper.search import find_matching_products, find_matching_terms


def test_find_matching_terms_is_case_insensitive_and_uses_substrings():
    assert find_matching_terms("Ein BETTkasten aus Holz", ("bett", "holz")) == (
        "bett",
        "holz",
    )


def test_find_matching_terms_returns_empty_tuple_without_match():
    assert find_matching_terms("Nur ein Regal", ("bett", "sofa")) == ()


def test_find_matching_products_returns_all_terms_per_product():
    product = ScrapedProduct(
        product_id="1",
        title="Tisch",
        price="10€",
        link="https://example.test/1",
        list_text="Tisch 10€ https://example.test/1",
        detail_text="Massivholz",
        search_text="Tisch 10€ https://example.test/1 Massivholz",
    )

    matches = find_matching_products([product], ("tisch", "holz", "bett"))

    assert len(matches) == 1
    assert matches[0].product == product
    assert matches[0].matched_terms == ("tisch", "holz")
