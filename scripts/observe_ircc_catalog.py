"""Research-only one-shot official IRCC form catalog observation.

Writes a review artifact; never commits, approves, maps or generates forms.
Usage: python -m scripts.observe_ircc_catalog --output reports/ircc-index.json
"""
import argparse
from datetime import date
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
        print("Official IRCC catalog observation failed safely:", exc, file=sys.stderr)
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
