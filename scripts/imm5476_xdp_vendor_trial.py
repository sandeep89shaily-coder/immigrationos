"""Build genuine-template XDP inputs and independently verify trial vendor PDFs.

Research-only. Fixed fictional names; never accepts arbitrary applicant data.
The official IMM5476 blank is fetched transiently by GitHub Actions and must
match the uploaded government PDF's pinned SHA-256 before any output is made.
"""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from pypdf import PdfReader
from app.imm5476_official_poc import (
    SOURCE_SHA256, _FIELDS, _find_xfa_packet,
    _parse_xml, _xfa_leaf, SYNTHETIC_VALUES,
)

_KEYS = ("applicant_family", "applicant_given",
         "representative_family", "representative_given")
_XDP = "http://ns.adobe.com/xdp/"
_XFA = "http://www.xfa.org/schema/xfa-data/1.0/"
ET.register_namespace("xdp", _XDP)
ET.register_namespace("xfa", _XFA)


def checked_blank(blank_path: Path) -> bytes:
    data = blank_path.read_bytes()
    if sha256(data).hexdigest() != SOURCE_SHA256 or len(data) > 12 * 1024 * 1024:
        raise ValueError("Official IMM5476 blank does not match approved SHA-256")
    return data


def prepare(blank: Path, out_dir: Path) -> None:
    checked_blank(blank)
    out_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(blank, strict=True)
    if len(reader.pages) != 4:
        raise ValueError("Official form page count changed")
    original = _find_xfa_packet(reader, "datasets").get_object().get_data()
    for variant in ("scalar", "rich"):
        root = _parse_xml(original)
        for key in _KEYS:
            binding = _FIELDS[key]
            if variant == "scalar" and key.endswith("_family"):
                # Preserve all surrounding form data but replace ONLY the
                # special XHTML value node with simple XFA element text.
                node_path = binding.xfa_path[:-3]
                surname = _xfa_leaf(root, node_path)
                for child in list(surname):
                    surname.remove(child)
                surname.text = SYNTHETIC_VALUES[key]
            else:
                _xfa_leaf(root, binding.xfa_path).text = SYNTHETIC_VALUES[key]
        xdp = ET.Element(f"{{{_XDP}}}xdp")
        xdp.append(root)
        xml = ET.tostring(xdp, encoding="utf-8", xml_declaration=True)
        parsed = _parse_xml(xml)
        if parsed.tag != f"{{{_XDP}}}xdp":
            raise ValueError("Invalid generated XDP envelope")
        for key in _KEYS:
            path = _FIELDS[key].xfa_path
            if variant == "scalar" and key.endswith("_family"):
                path = path[:-3]
            if _xfa_leaf(parsed[0], path).text != SYNTHETIC_VALUES[key]:
                raise ValueError("Incorrect fictional XDP field: " + key)
        (out_dir / f"fictional-{variant}.xdp").write_bytes(xml)
    print("Prepared two genuine-template, data-only XDP files; NO PDF modifications")


def verify(blank: Path, filled: Path, report: Path) -> bool:
    original = checked_blank(blank)
    result = {"official_template_pinned": True,
              "output_path": filled.name,
              "adobe_acrobat_tested": False,
              "official_validated": False,
              "submission_ready": False}
    try:
        data = filled.read_bytes()
        if len(data) > 20 * 1024 * 1024 or not data.startswith(b"%PDF-"):
            raise ValueError("Not a reasonable generated PDF")
        result["output_sha256"] = sha256(data).hexdigest()
        result["original_pdf_byte_prefix_preserved"] = data.startswith(original)
        reader = PdfReader(filled, strict=False)
        result["pages"] = len(reader.pages)
        fields = reader.get_fields() or {}
        try:
            ds = _find_xfa_packet(reader, "datasets").get_object().get_data()
            root = _parse_xml(ds)
            xfa_values = {}
            for key in _KEYS:
                name = _FIELDS[key].acroform_name
                # Scalar XFA has no XHTML descendant path. Do not try to
                # resolve it until deciding which XDP encoding was saved.
                if key.endswith("_family"):
                    parent = _xfa_leaf(root, _FIELDS[key].xfa_path[:-3])
                    value = (parent.text if len(parent) == 0 else
                             _xfa_leaf(root, _FIELDS[key].xfa_path).text)
                else:
                    value = _xfa_leaf(root, _FIELDS[key].xfa_path).text
                xfa_values[key] = value == SYNTHETIC_VALUES[key]
            result["xfa_matches"] = xfa_values
        except Exception as exc:
            result["xfa_error"] = type(exc).__name__ + ": " + str(exc)[:120]
        result["acroform_matches"] = {
            key: str(fields.get(_FIELDS[key].acroform_name, {}).get("/V", "")) ==
                 SYNTHETIC_VALUES[key] for key in _KEYS
        }
        xfa = result.get("xfa_matches", {})
        result["all_xfa_match"] = len(xfa) == 4 and all(xfa.values())
        result["all_acroform_match"] = all(result["acroform_matches"].values())
        result["status"] = ("both_layers_pass" if
                            result["pages"] == 4 and result["all_xfa_match"]
                            and result["all_acroform_match"] else
                            "structural_or_data_mismatch")
    except Exception as exc:
        result.update(status="readback_error", error_type=type(exc).__name__,
                      error=str(exc)[:250])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return result["status"] == "both_layers_pass"


def main() -> None:
    p = ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("original", type=Path)
    a.add_argument("out_dir", type=Path)
    b = sub.add_parser("verify")
    b.add_argument("original", type=Path)
    b.add_argument("filled", type=Path)
    b.add_argument("report", type=Path)
    args = p.parse_args()
    if args.cmd == "prepare":
        prepare(args.original, args.out_dir)
    elif not verify(args.original, args.filled, args.report):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
