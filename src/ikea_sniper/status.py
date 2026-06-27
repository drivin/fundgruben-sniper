from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ikea_sniper.search import ProductSearchResult


STATUS_FILE_NAME = "reported-products.json"


class StatusStoreError(RuntimeError):
    pass


@dataclass
class ReportStatus:
    reported_product_ids: set[str]

    def remove_missing(self, current_product_ids: set[str]) -> set[str]:
        removed_product_ids = self.reported_product_ids - current_product_ids
        self.reported_product_ids.intersection_update(current_product_ids)
        return removed_product_ids

    def mark_reported(self, product_ids: set[str]) -> None:
        self.reported_product_ids.update(product_ids)


@dataclass(frozen=True)
class DuplicateFilterResult:
    new_matches: list[ProductSearchResult]
    already_reported_matches: list[ProductSearchResult]
    removed_product_ids: set[str]


class ProductStatusStore:
    def __init__(self, status_dir: Path) -> None:
        self._status_file = status_dir / STATUS_FILE_NAME

    @property
    def status_file(self) -> Path:
        return self._status_file

    def load(self) -> ReportStatus:
        if not self._status_file.exists():
            return ReportStatus(reported_product_ids=set())

        try:
            with self._status_file.open("r", encoding="utf-8") as file:
                raw_status = json.load(file)
        except OSError as error:
            raise StatusStoreError(
                f"Status file could not be read: {self._status_file}"
            ) from error
        except json.JSONDecodeError as error:
            raise StatusStoreError(
                f"Status file does not contain valid JSON: {self._status_file}"
            ) from error

        if not isinstance(raw_status, dict):
            raise StatusStoreError(
                "Status file must contain a JSON object."
            )

        reported_product_ids = raw_status.get("reported_product_ids")
        if not isinstance(reported_product_ids, list):
            raise StatusStoreError(
                "Status file must contain a `reported_product_ids` list."
            )

        return ReportStatus(
            reported_product_ids={
                str(product_id).strip()
                for product_id in reported_product_ids
                if str(product_id).strip()
            }
        )

    def save(self, status: ReportStatus) -> None:
        self._status_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_status_file = self._status_file.with_suffix(".tmp")
        payload = {
            "reported_product_ids": sorted(status.reported_product_ids),
        }

        try:
            with temporary_status_file.open("w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2)
                file.write("\n")
            temporary_status_file.replace(self._status_file)
        except OSError as error:
            raise StatusStoreError(
                f"Status file could not be written: {self._status_file}"
            ) from error


def filter_new_matches(
    matches: list[ProductSearchResult],
    status: ReportStatus,
    current_product_ids: set[str],
) -> DuplicateFilterResult:
    removed_product_ids = status.remove_missing(current_product_ids)
    new_matches = []
    already_reported_matches = []

    for match in matches:
        if match.product.product_id in status.reported_product_ids:
            already_reported_matches.append(match)
        else:
            new_matches.append(match)

    return DuplicateFilterResult(
        new_matches=new_matches,
        already_reported_matches=already_reported_matches,
        removed_product_ids=removed_product_ids,
    )
