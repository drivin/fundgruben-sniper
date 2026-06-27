from __future__ import annotations

import pytest

from ikea_sniper.scraper import ScrapedProduct
from ikea_sniper.search import ProductSearchResult
from ikea_sniper.status import (
    ProductStatusStore,
    ReportStatus,
    StatusStoreError,
    filter_new_matches,
)


def product(product_id: str) -> ScrapedProduct:
    return ScrapedProduct(
        product_id=product_id,
        title=f"Product {product_id}",
        price="1€",
        link=f"https://example.test/{product_id}",
        list_text=f"Product {product_id}",
        detail_text="",
        search_text=f"Product {product_id}",
    )


def test_status_store_saves_and_loads_reported_product_ids(tmp_path):
    store = ProductStatusStore(tmp_path)
    store.save(ReportStatus({"2", "1"}))

    loaded = store.load()

    assert loaded.reported_product_ids == {"1", "2"}


def test_status_store_rejects_invalid_json_structure(tmp_path):
    (tmp_path / "reported-products.json").write_text("[]", encoding="utf-8")
    store = ProductStatusStore(tmp_path)

    with pytest.raises(StatusStoreError):
        store.load()


def test_filter_new_matches_removes_missing_ids_and_splits_duplicates():
    p1 = product("1")
    p2 = product("2")
    status = ReportStatus({"1", "9"})
    matches = [
        ProductSearchResult(p1, ("one",)),
        ProductSearchResult(p2, ("two",)),
    ]

    result = filter_new_matches(matches, status, {"1", "2"})

    assert [match.product.product_id for match in result.new_matches] == ["2"]
    assert [match.product.product_id for match in result.already_reported_matches] == [
        "1"
    ]
    assert result.removed_product_ids == {"9"}
    assert status.reported_product_ids == {"1"}


def test_mark_reported_updates_status_after_successful_delivery():
    status = ReportStatus(set())

    status.mark_reported({"1"})

    assert status.reported_product_ids == {"1"}
