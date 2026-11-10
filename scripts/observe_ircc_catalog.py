"""Research-only one-shot official IRCC form catalog observation.

Writes a review artifact; never commits, approves, maps or generates forms.
Usage: python -m scripts.observe_ircc_catalog --output reports/ircc-index.json
"""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

from app.catalog_import import CatalogError, fetch_official_catalog, snapshot_document


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    try:
        records, bytes_read = fetch_official_catalog()
        snapshot = snapshot_document(records, date.today().isoformat())
    except (CatalogError, OSError, ValueError, UnicodeError) as exc:
        # Persist blocked source observations; never approve or publish data.
        reason = str(exc) if isinstance(exc, CatalogError) else type(exc).__name__
        args.output.parent.mkdir(parents=True, exist_ok=True)
        failure = {
            "source": "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides.html",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked_official_index_not_parsed",
            "blocker": reason[:180],
            "review_state": "unreviewed",
            "catalog_entries_accepted": 0,
            "generated_or_validated_form_count": 0,
            "automatic_catalog_publication": False,
        }
        args.output.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        args.output.with_suffix(".md").write_text(
            "# IRCC index observation blocked\n\n"
            "No forms were accepted, mapped or published. Manual official-source review required.\n\n"
            f"Blocker: {reason[:180]}\n",
            encoding="utf-8")
        print("Official IRCC catalog observation failed safely:", reason, file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = args.output.with_suffix(".md")
    summary.write_text(
        "# IRCC catalog research observation\n\n"
        f"- Date: {snapshot['observed_on']}\n"
        f"- Official index entries discovered: {snapshot['catalog_entries']}\n"
        f"- Index response bytes: {bytes_read}\n"
        f"- Snapshot SHA-256: `{snapshot['source_table_sha256']}`\n"
        "- Status: **UNREVIEWED**. The index can include checklists, guides and inactive pathways.\n"
        "- Field mappings approved: **0** by this observation.\n"
        "- Official PDF generation validated: **0** by this observation.\n"
        "- All records require contextual and version-specific review before product inclusion.\n",
        encoding="utf-8")
    print("Discovered", snapshot["catalog_entries"], "official index entries; no forms approved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
