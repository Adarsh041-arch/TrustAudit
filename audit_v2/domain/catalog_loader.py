"""Catalog loader: parse the machine-readable check catalog from YAML."""
from __future__ import annotations

from pathlib import Path

import yaml

from audit_v2.domain.models import CheckCatalog, CheckCatalogEntry

CATALOG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "contracts"
    / "check_catalog.yaml"
)


def load_catalog(path: Path | None = None) -> CheckCatalog:
    """Load the machine-readable check catalog from YAML.

    Returns a parsed CheckCatalog. Raises FileNotFoundError if missing.
    """
    catalog_path = path or CATALOG_PATH
    if not catalog_path.exists():
        raise FileNotFoundError(f"Check catalog not found: {catalog_path}")
    with open(catalog_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return CheckCatalog(**data)


def entries_by_id(catalog: CheckCatalog) -> dict[str, CheckCatalogEntry]:
    return {entry.check_id: entry for entry in catalog.checks}


__all__ = ["load_catalog", "entries_by_id"]
