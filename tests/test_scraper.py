from __future__ import annotations

import pytest

from ikea_sniper.errors import ScrapingError
from ikea_sniper.scraper import (
    _build_api_page_url,
    _items_from_grouped_search_payload,
    _product_from_list_item,
    extract_product_id,
    ProductListItem,
)


def test_extract_product_id_from_example_link():
    product_id = extract_product_id(
        "https://www.ikea.com/de/de/second-hand/buy-from-ikea/#/kassel/868508117"
    )

    assert product_id == "868508117"


def test_extract_product_id_accepts_query_suffix():
    product_id = extract_product_id(
        "https://www.ikea.com/de/de/second-hand/buy-from-ikea/#/kassel/868508117?x=1"
    )

    assert product_id == "868508117"


def test_extract_product_id_rejects_link_without_id():
    with pytest.raises(ScrapingError):
        extract_product_id(
            "https://www.ikea.com/de/de/second-hand/buy-from-ikea/#/kassel"
        )


def test_build_api_page_url_preserves_existing_query_parameters():
    page_url = _build_api_page_url(
        "https://web-api.ikea.com/circular/circular-asis/offers/grouped/search"
        "?languageCode=de&size=32&storeIds=174&page=0",
        3,
    )

    assert page_url == (
        "https://web-api.ikea.com/circular/circular-asis/offers/grouped/search"
        "?languageCode=de&size=32&storeIds=174&page=3"
    )


def test_items_from_grouped_search_payload_maps_api_groups_to_product_items():
    payload = {
        "content": [
            {
                "articleNumbers": ["40518425"],
                "title": "LILLEHEM",
                "description": "Bein, 20 cm, Metall",
                "currency": "EUR",
                "minPrice": 6.49,
                "maxPrice": 9.99,
                "offers": [
                    {
                        "offerNumber": "856136850",
                        "description": "Bein, 20 cm, Metall",
                        "additionalInfo": "Originalverpackt",
                        "productConditionTitle": "Brandneu",
                        "reasonDiscount": "Kundenrueckgabe",
                    }
                ],
            },
            {
                "title": "BROKEN",
                "currency": "EUR",
                "minPrice": 1,
                "maxPrice": 1,
                "offers": [],
            },
        ]
    }

    items = _items_from_grouped_search_payload(
        payload,
        "kassel",
        "https://www.ikea.com/de/de/second-hand/buy-from-ikea/#/kassel",
    )

    assert len(items) == 1
    assert items[0].product_id == "856136850"
    assert items[0].title == "LILLEHEM"
    assert items[0].price == "6.49€ - 9.99€"
    assert items[0].link == (
        "https://www.ikea.com/de/de/second-hand/buy-from-ikea/#/kassel/856136850"
    )
    assert "Originalverpackt" in items[0].list_text
    assert "40518425" in items[0].list_text


def test_product_from_list_item_uses_list_text_without_detail_text():
    product = _product_from_list_item(
        ProductListItem(
            product_id="856136850",
            title="LILLEHEM",
            price="6.49€",
            link="https://example.test/#/kassel/856136850",
            list_text="LILLEHEM Originalverpackt 6.49€",
        )
    )

    assert product.product_id == "856136850"
    assert product.detail_text == ""
    assert product.search_text == "LILLEHEM Originalverpackt 6.49€"
