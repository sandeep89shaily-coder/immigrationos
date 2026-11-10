"""Blocked official index observations must remain auditable and fail closed."""
import json
import sys

from app.catalog_import import CatalogError
from scripts import observe_ircc_catalog


def test_blocked_catalog_observation_writes_unreviewed_report(tmp_path, monkeypatch):
    def reject():
        raise CatalogError("Invalid form code, title or modification date in official index")
    monkeypatch.setattr(observe_ircc_catalog, "fetch_official_catalog", reject)
    target = tmp_path / "reports" / "ircc-index.json"
    monkeypatch.setattr(sys, "argv", ["observe_ircc_catalog", "--output", str(target)])
    assert observe_ircc_catalog.main() == 1
    report = json.loads(target.read_text())
    assert report["status"] == "blocked_official_index_not_parsed"
    assert report["catalog_entries_accepted"] == 0
    assert report["generated_or_validated_form_count"] == 0
    assert report["automatic_catalog_publication"] is False
    assert "Manual official-source review required" in target.with_suffix(".md").read_text()
