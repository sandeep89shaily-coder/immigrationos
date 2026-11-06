"""Inspect a *blank* locally downloaded official form without uploading it to a service.

Usage:
python -m scripts.inspect_ircc_form --input C:\Forms\imm5476e.pdf --form-code IMM5476 --output inspection.json

This classification does not validate any government form.
"""
import argparse
import json
from pathlib import Path

from app.form_template_inspector import MAX_TEMPLATE_BYTES, TemplateInspectionError, inspect_pdf_template


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect blank form PDF structure (review only)")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--form-code", type=str, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        with args.input.open("rb") as f:
            raw = f.read(MAX_TEMPLATE_BYTES + 1)
        report = inspect_pdf_template(raw)
    except (OSError, TemplateInspectionError) as exc:
        print(f"Inspection could not be completed: {exc}")
        return 1

    report["declared_form_code"] = args.form_code.strip().upper().replace(" ", "")
    report["declared_form_code_verified"] = False
    report["source_url_verified"] = False
    report["bytes_persisted_by_inspector"] = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Technical classification:", report["classification"])
    print("Official IRCC validation: NOT PERFORMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
