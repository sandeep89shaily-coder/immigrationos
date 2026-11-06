"""Observe the official blank IMM 5476 PDF (research-only, no client data).

python -m scripts.observe_imm5476_template --output reports/imm5476-observation.json
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from app.official_template_observation import (
    OfficialTemplateObservationError, download_published_blank, observe_blank_template,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", type=str, default=None)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw = download_published_blank()
        result = observe_blank_template(raw, pinned_sha256=args.expected_sha256)
        result["source_fetch_status"] = "downloaded_for_transient_inspection"
        code = 0
    except OfficialTemplateObservationError:
        result = {
            "form_code": "IMM5476",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source_fetch_status": "unavailable_or_not_inspectable",
            "release_approved": False,
            "official_autofill_supported": False,
            "submission_supported": False,
            "warning": "Government-source access or PDF inspection failed. No form status changed.",
        }
        code = 1
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("IMM5476 public template observation:", result["source_fetch_status"])
    print("IRCC form autofill/release approved: NO")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
