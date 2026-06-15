from __future__ import annotations

import pytest

from ikea_sniper.errors import ScrapingError
from ikea_sniper.scraper import extract_product_id


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
