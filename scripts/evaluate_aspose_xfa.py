"""Isolated third-party XFA compatibility trial; never used in ImmigrationOS production.

Target: original blank IRCC IMM5476 (11-2025) with known SHA-256.
Output: fixed fictional data only, explicitly NOT ready for IRCC submission.

Run with an *optional* commercial Aspose.PDF Python/.NET installation:
    pip install 'aspose-pdf==26.9.0'
    python -m scripts.evaluate_aspose_xfa --input /path/to/imm5476e.pdf \\
        --output /tmp/aspose-imm5476-UNVALIDATED.pdf --report /tmp/aspose-result.json

This is deliberately an isolated SDK evaluation, not a fallback to pypdf,
PyMuPDF, XFA flattening, AcroForm-only filling or barcode fabrication.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import traceback

from app.imm5476_official_poc import (
    _FIELDS, _find_xfa_packet, _parse_xml, _xfa_leaf,
    SOURCE_SHA256, SYNTHETIC_VALUES,
)

# Keep trial at or below four mapped fields; unlicensed Aspose evaluations
# may restrict collection traversal and watermark generated output.
TARGET_KEYS = (
    "applicant_family", "applicant_given",
    "representative_family", "representative_given",
)
MAX_SOURCE_BYTES = 12 * 1024 * 1024


class AsposeTrialBlocked(RuntimeError):
    pass


def resolve_field_names(inventory, requested=TARGET_KEYS):
    """Select only unambiguous, observed names. Never guess unknown XFA paths."""
    result = {}
    present = [str(x) for x in inventory]
    for key in requested:
        expected = _FIELDS[key].acroform_name
        hits = [name for name in present
                if name == expected or name.endswith("." + expected)]
        if len(hits) == 1:
            result[key] = hits[0]
        elif len(hits) > 1:
            raise AsposeTrialBlocked("Ambiguous XFA field inventory: " + key)
    return result


def inspect_output(output: Path, mapped: dict) -> dict:
    """Independent structural readback. Does not certify Adobe XFA behavior."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(output), strict=True)
        if len(reader.pages) != 4:
            return {"readback": "wrong_page_count", "pages": len(reader.pages)}
        acro = reader.get_fields() or {}
        root = _parse_xml(_find_xfa_packet(reader, "datasets").get_object().get_data())
        verification = {}
        for key in mapped:
            binding = _FIELDS[key]
            xfa_text = _xfa_leaf(root, binding.xfa_path).text
            acro_text = str(acro.get(binding.acroform_name, {}).get("/V", ""))
            verification[key] = {
                "xfa_matches": xfa_text == SYNTHETIC_VALUES[key],
                "acroform_matches": acro_text == SYNTHETIC_VALUES[key],
            }
        perm = reader.trailer["/Root"].get("/Perms")
        return {
            "readback": "completed",
            "pages": len(reader.pages),
            "xfa_and_acroform": verification,
            "ur3_marker_present": bool(perm and "/UR3" in perm.get_object()),
            "all_xfa_values_match": bool(verification) and all(
                status["xfa_matches"] for status in verification.values()),
        }
    except Exception as exc:
        return {"readback": "error", "error_type": type(exc).__name__}


def run_trial(input_path: Path, output_path: Path) -> dict:
    """SDK does all PDF writing; no fallback if its XFA support fails."""
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path or output_path.exists():
        raise AsposeTrialBlocked("Must use a new, separate output path")
    blob = input_path.read_bytes()
    if len(blob) > MAX_SOURCE_BYTES or sha256(blob).hexdigest() != SOURCE_SHA256:
        raise AsposeTrialBlocked("Official PDF SHA-256 mismatch; refusing to touch template")
    import aspose.pdf as ap  # optional commercial dependency; only in isolated CLI

    report = {
        "engine": "Aspose.PDF for Python via .NET (evaluation)",
        "form_code": "IMM5476",
        "template_revision": "11-2025",
        "source_sha256": SOURCE_SHA256,
        "test_data": "fictional_only",
        "official_validation": False,
        "adobe_reader_tested": False,
        "ready_for_submission": False,
    }
    document = ap.Document(str(input_path))
    try:
        xfa = document.form.xfa
        names = [str(name) for name in xfa.field_names]
        report["xfa_field_inventory_count"] = len(names)
        report["engine_can_enumerate_xfa"] = bool(names)
        selected = resolve_field_names(names)
        report["mapped_keys"] = sorted(selected)
        report["requested_keys"] = list(TARGET_KEYS)
        if not selected:
            report["status"] = "no_matching_xfa_fields_visible_in_trial"
            report["note"] = "Evaluation collection limit or XFA naming differs from canonical PDF fields"
            return report
        for key, vendor_name in selected.items():
            xfa[vendor_name] = SYNTHETIC_VALUES[key]
        document.save(str(output_path))
    finally:
        document.dispose()

    if not output_path.is_file() or not output_path.read_bytes().startswith(b"%PDF-"):
        report["status"] = "vendor_failed_to_save_pdf"
        return report
    report["output_sha256"] = sha256(output_path.read_bytes()).hexdigest()
    report.update(inspect_output(output_path, selected))
    report["status"] = (
        "xfa_values_written_and_read_back"
        if report.get("all_xfa_values_match") else "xfa_values_unverified_or_changed"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "engine": "aspose_pdf",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "not_tested",
        "official_validation": False,
        "adobe_reader_tested": False,
        "ready_for_submission": False,
    }
    try:
        result.update(run_trial(args.input, args.output))
        code = 0 if result["status"] == "xfa_values_written_and_read_back" else 2
    except (AsposeTrialBlocked, ImportError, OSError, AttributeError, TypeError, ValueError) as exc:
        result.update({"status": "blocked_or_failed",
                       "error_type": type(exc).__name__,
                       "error_description": str(exc)[:350]})
        code = 2
    except Exception as exc:
        # Keep vendor crashes and opaque errors visible without dumping PDF contents.
        result.update({"status": "vendor_exception",
                       "error_type": type(exc).__name__,
                       "error_description": str(exc)[:350]})
        code = 2
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
